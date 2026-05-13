from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    DiamondPriceLookupRequest,
    DiamondPriceLookupResponse,
    DropdownOptionsResponse,
    MetalRateResponse,
    QuoteRequest,
    QuoteResponse,
)

_TWO = Decimal("0.01")

# Sourced from Settings sheet, column D (Item Types)
_JEWELLERY_ITEM_TYPES = ["Ring", "Necklace", "Earrings", "Jhumki", "Bracelet", "Pendant"]


async def lookup_diamond_price(
    session: AsyncSession, req: DiamondPriceLookupRequest
) -> DiamondPriceLookupResponse:
    result = await session.execute(
        text("""
            SELECT karigar_price, vendor_price, vendor_name,
                   avg_weight_carat, mm_size, company_grade
            FROM diamond_inventory
            WHERE item_type      = :item_type
              AND batch          = :batch
              AND shape          = :shape
              AND karigar_color  = :karigar_color
              AND karigar_purity = :karigar_purity
              AND (:sieve_size IS NULL OR sieve_size = :sieve_size)
            ORDER BY karigar_price DESC
            LIMIT 1
        """).bindparams(bindparam("sieve_size", type_=String())),
        {
            "item_type":      req.item_type,
            "batch":          req.batch,
            "shape":          req.shape,
            "karigar_color":  req.karigar_color,
            "karigar_purity": req.karigar_purity,
            "sieve_size":     req.sieve_size,
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No matching diamond found for the given parameters",
        )
    return DiamondPriceLookupResponse(**row)


async def _get_gold_rate(session: AsyncSession, purity_kt: int) -> Decimal:
    result = await session.execute(
        text("""
            SELECT price_per_gram FROM metal_rates
            WHERE metal_type = 'Gold'
              AND purity_kt  = :purity
        """),
        {"purity": purity_kt},
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No gold rate found for {purity_kt}kt",
        )
    return Decimal(str(row[0]))


async def _get_settings(session: AsyncSession) -> dict[str, Decimal]:
    result = await session.execute(text("SELECT key, value FROM pricing_settings"))
    return {r[0]: Decimal(str(r[1])) for r in result.all()}


async def calculate_quote(session: AsyncSession, req: QuoteRequest) -> QuoteResponse:
    diamond = await lookup_diamond_price(
        session,
        DiamondPriceLookupRequest(
            item_type=req.item_type,
            batch=req.batch,
            shape=req.shape,
            karigar_color=req.karigar_color,
            karigar_purity=req.karigar_purity,
            sieve_size=req.sieve_size,
        ),
    )
    diamond_value = Decimal(diamond.karigar_price) * req.total_carat_weight

    gold_rate = await _get_gold_rate(session, req.gold_purity_kt)
    gold_value = gold_rate * req.gold_weight_grams

    cfg = await _get_settings(session)
    labour_per_gram = cfg.get("labour_per_gram", Decimal("1000"))
    markup_pct = cfg.get("markup_pct", Decimal("0.15"))
    gst_pct = cfg.get("gst_pct", Decimal("0.03"))

    making = req.making_charges if req.making_charges is not None else labour_per_gram * req.gold_weight_grams

    subtotal = gold_value + making + diamond_value
    markup_amount = subtotal * markup_pct
    after_markup = subtotal + markup_amount
    gst_amount = after_markup * gst_pct
    final_price = after_markup + gst_amount

    return QuoteResponse(
        diamond_price_per_carat=diamond.karigar_price,
        diamond_value=diamond_value.quantize(_TWO),
        gold_rate_per_gram=gold_rate,
        gold_value=gold_value.quantize(_TWO),
        making_charges=making.quantize(_TWO),
        subtotal=subtotal.quantize(_TWO),
        markup_amount=markup_amount.quantize(_TWO),
        after_markup=after_markup.quantize(_TWO),
        gst_amount=gst_amount.quantize(_TWO),
        final_price=final_price.quantize(_TWO),
    )


async def get_dropdown_options(
    session: AsyncSession,
    item_type:      str | None = None,
    batch:          str | None = None,
    shape:          str | None = None,
    karigar_color:  str | None = None,
    karigar_purity: str | None = None,
) -> DropdownOptionsResponse:
    async def distinct(col: str, active: dict[str, str | None]) -> list[str]:
        """Return distinct non-null values for `col` filtered by whatever keys in `active` are set."""
        conditions = [f"{col} IS NOT NULL"]
        params: dict[str, str] = {}
        for k, v in active.items():
            if v is not None:
                conditions.append(f"{k} = :{k}")
                params[k] = v
        where = " AND ".join(conditions)
        result = await session.execute(
            text(f"SELECT DISTINCT {col} FROM diamond_inventory WHERE {where} ORDER BY {col}"),
            params,
        )
        return [str(r[0]) for r in result.all()]

    purity_result = await session.execute(
        text("SELECT DISTINCT purity_kt FROM metal_rates WHERE metal_type = 'Gold' ORDER BY purity_kt DESC")
    )
    gold_purity_options = [r[0] for r in purity_result.all()]

    return DropdownOptionsResponse(
        item_types=await distinct("item_type", {}),
        batches=await distinct("batch", {
            "item_type": item_type,
        }),
        shapes=await distinct("shape", {
            "item_type": item_type,
            "batch":     batch,
        }),
        karigar_colors=await distinct("karigar_color", {
            "item_type": item_type,
            "batch":     batch,
            "shape":     shape,
        }),
        karigar_purities=await distinct("karigar_purity", {
            "item_type":     item_type,
            "batch":         batch,
            "shape":         shape,
            "karigar_color": karigar_color,
        }),
        sieve_sizes=await distinct("sieve_size", {
            "item_type":      item_type,
            "batch":          batch,
            "shape":          shape,
            "karigar_color":  karigar_color,
            "karigar_purity": karigar_purity,
        }),
        gold_purity_options=gold_purity_options,
        jewellery_item_types=_JEWELLERY_ITEM_TYPES,
    )


async def list_metal_rates(session: AsyncSession) -> list[MetalRateResponse]:
    result = await session.execute(
        text("""
            SELECT metal_type, purity_kt, colour, price_per_gram
            FROM metal_rates ORDER BY metal_type, purity_kt
        """)
    )
    return [MetalRateResponse(**dict(r._mapping)) for r in result.all()]
