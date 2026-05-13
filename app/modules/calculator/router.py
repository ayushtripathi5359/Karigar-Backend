from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db_anonymous

from .schemas import (
    DiamondPriceLookupRequest,
    DiamondPriceLookupResponse,
    DropdownOptionsResponse,
    MetalRateResponse,
    QuoteRequest,
    QuoteResponse,
)
from . import service

router = APIRouter(prefix="/v1/calculator", tags=["calculator"])

DbDep = Annotated[AsyncSession, Depends(get_db_anonymous)]


@router.get("/options", response_model=DropdownOptionsResponse)
async def dropdown_options(
    db:             DbDep,
    item_type:      str | None = Query(default=None),
    batch:          str | None = Query(default=None),
    shape:          str | None = Query(default=None),
    karigar_color:  str | None = Query(default=None),
    karigar_purity: str | None = Query(default=None),
):
    """
    Cascading dropdown values. Each field is filtered by the upstream selections
    so only combinations that exist in diamond_inventory are returned.
    """
    return await service.get_dropdown_options(
        db,
        item_type=item_type,
        batch=batch,
        shape=shape,
        karigar_color=karigar_color,
        karigar_purity=karigar_purity,
    )


@router.get("/metal-rates", response_model=list[MetalRateResponse])
async def metal_rates(db: DbDep):
    """Current gold / silver rates per gram."""
    return await service.list_metal_rates(db)


@router.post("/diamond-price", response_model=DiamondPriceLookupResponse)
async def diamond_price(req: DiamondPriceLookupRequest, db: DbDep):
    """Look up Karigar price per carat for a specific diamond combination."""
    return await service.lookup_diamond_price(db, req)


@router.post("/quote", response_model=QuoteResponse)
async def jewellery_quote(req: QuoteRequest, db: DbDep):
    """
    Calculate full jewellery price:
    gold value + making charges + diamond value → markup → GST → final price.
    """
    return await service.calculate_quote(db, req)
