"""Explicit conditional capital bridges; no financing capacity is inferred."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=40)]
Positive = Annotated[Decimal, Field(gt=0, max_digits=40)]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False)


class ObligationChange(_Record):
    cash_proceeds: Nonnegative
    fees: Nonnegative
    noncash_additions: Nonnegative
    principal_payments: Nonnegative
    converted_principal: Nonnegative
    conversion_price: Positive | None

    @model_validator(mode='after')
    def terms(self):
        if self.fees > self.cash_proceeds:
            raise ValueError('financing fees exceed explicit proceeds')
        if (self.converted_principal > 0) != (self.conversion_price is not None):
            raise ValueError('conversion requires principal and explicit positive conversion price together')
        return self


class ForwardCapital(_Record):
    version: Literal['forward_capital_v1']
    unit: str = Field(min_length=3, max_length=3)
    period_start: date
    capital_date: date
    operating_cash_flow: Decimal = Field(max_digits=40)
    operating_cash_flow_basis: Literal['after_interest_and_operating_lease_payments']
    cash_capex: Nonnegative
    acquisitions: Nonnegative
    equity_proceeds: Nonnegative
    equity_fees: Nonnegative
    equity_issue_price: Positive | None
    other_dilution_shares: Nonnegative
    obligation_changes: dict[str, ObligationChange] = Field(max_length=5)
    operating_assumptions: str = Field(min_length=1, max_length=1200)
    cash_conversion_rationale: str = Field(min_length=1, max_length=1200)
    funding_rationale: str = Field(min_length=1, max_length=1200)

    @model_validator(mode='after')
    def terms(self):
        if self.period_start > self.capital_date:
            raise ValueError('capital bridge interval reversed')
        if self.equity_fees > self.equity_proceeds:
            raise ValueError('equity fees exceed explicit proceeds')
        if (self.equity_proceeds > 0) != (self.equity_issue_price is not None):
            raise ValueError('equity issuance requires proceeds and explicit positive issue price together')
        if not all(v.strip() for v in (self.operating_assumptions, self.cash_conversion_rationale, self.funding_rationale)):
            raise ValueError('operating, cash conversion and funding assumptions must be explicit')
        return self


class CapitalResult(_Record):
    closing_cash: Decimal
    closing_obligations: Decimal
    shares_outstanding: Decimal
    net_obligations: Decimal
    capital_date: date
    funding_gap: Decimal
    funding_assumptions: tuple[str, ...]


def calculate_forward_capital(funding: ForwardCapital, *, snapshot_date: date,
                              forecast_end: date, as_of: date, unit: str,
                              opening_cash: Decimal, opening_shares: Decimal,
                              opening_obligations: dict[str, Decimal]) -> CapitalResult:
    """Apply assumptions to already validated, nonoverlapping opening facts.

    Cash capex excludes noncash asset additions. CFO includes interest and all
    operating-lease cash payments. Operating-lease principal reduces obligations
    here but is not deducted from cash a second time.
    """
    funding = ForwardCapital.model_validate(funding.model_dump())
    if funding.unit != unit:
        raise ValueError('capital bridge and source currency differ')
    if (funding.period_start != snapshot_date + timedelta(days=1)
            or funding.capital_date != forecast_end or funding.capital_date <= as_of):
        raise ValueError('capital bridge must cover snapshot through the future forecast end')
    if set(funding.obligation_changes) != set(opening_obligations):
        raise ValueError('capital movements must explicitly cover every declared obligation category')
    if (opening_cash < 0 or opening_shares <= 0
            or any(v < 0 or not v.is_finite() for v in opening_obligations.values())):
        raise ValueError('invalid opening capital')
    with localcontext() as context:
        context.prec = 60
        cash = (opening_cash + funding.operating_cash_flow - funding.cash_capex
                - funding.acquisitions + funding.equity_proceeds - funding.equity_fees)
        shares = opening_shares + funding.other_dilution_shares
        if funding.equity_issue_price is not None:
            shares += funding.equity_proceeds / funding.equity_issue_price
        obligations = Decimal(0)
        lines = [
            f'Forward capital assumptions for {funding.period_start} to {funding.capital_date}; currency {unit}.',
            f'Operating assumptions (unvalidated): {funding.operating_assumptions}',
            f'Cash-conversion assumption (unvalidated): {funding.cash_conversion_rationale}',
            f'Funding assumption (unvalidated): {funding.funding_rationale}',
            'Operating cash flow includes interest and operating-lease cash payments; cash capex excludes noncash additions.',
            f'Cash: opening {opening_cash} + operating cash {funding.operating_cash_flow} - cash capex {funding.cash_capex} - acquisitions {funding.acquisitions} + equity proceeds {funding.equity_proceeds} - equity fees {funding.equity_fees}.',
            f'Equity issue price {funding.equity_issue_price}; other actual-share dilution {funding.other_dilution_shares}; not an EPS weighted-average denominator.',
        ]
        for category, movement in funding.obligation_changes.items():
            if category == 'borrowings':
                if movement.noncash_additions:
                    raise ValueError('borrowings require explicit cash proceeds, not unexplained noncash additions')
            elif (movement.cash_proceeds or movement.fees or movement.converted_principal):
                raise ValueError('lease/equipment additions are noncash and cannot create cash proceeds or conversion shares')
            available = opening_obligations[category] + movement.cash_proceeds + movement.noncash_additions
            reduction = movement.principal_payments + movement.converted_principal
            if reduction > available:
                raise ValueError('principal and conversion reductions exceed supported category balance')
            obligations += available - reduction
            cash += movement.cash_proceeds - movement.fees
            if category != 'operating_leases':
                cash -= movement.principal_payments
            if movement.conversion_price is not None:
                shares += movement.converted_principal / movement.conversion_price
            lines.append(f'{category}: opening {opening_obligations[category]} + proceeds {movement.cash_proceeds} + noncash additions {movement.noncash_additions} - principal {movement.principal_payments} - conversion {movement.converted_principal} = {available - reduction}; fees {movement.fees}; conversion price {movement.conversion_price}.')
        gap = max(-cash, Decimal(0))
        if gap:
            lines.append(f'Unfunded cash shortfall {gap} {unit}; no financing plug or additional shares assumed. Valuation is conditional on this unresolved funding need.')
        return CapitalResult(closing_cash=cash, closing_obligations=obligations,
                             shares_outstanding=shares, net_obligations=obligations-cash,
                             capital_date=funding.capital_date, funding_gap=gap,
                             funding_assumptions=tuple(lines))
