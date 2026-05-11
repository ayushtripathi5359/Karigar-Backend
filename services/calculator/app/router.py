from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from karigar_shared.db.deps import get_db_anonymous

from . import service
from .schemas import (
    DiamondPriceLookupRequest,
    DiamondPriceLookupResponse,
    DropdownOptionsResponse,
    MetalRateResponse,
    QuoteRequest,
    QuoteResponse,
)

router = APIRouter(prefix="/v1/calculator", tags=["calculator"])

DbDep = Annotated[AsyncSession, Depends(get_db_anonymous)]


@router.get("/options", response_model=DropdownOptionsResponse)
async def dropdown_options(db: DbDep):
    """Valid dropdown values for item type, shape, colour grade, etc."""
    return await service.get_dropdown_options(db)


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
    gold value + making charges + diamond value → markup → GST → optional discount.
    """
    return await service.calculate_quote(db, req)
