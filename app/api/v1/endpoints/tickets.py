"""Support ticket HTTP endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.dependencies import TicketServiceDep
from app.schemas.common import ErrorResponse
from app.schemas.ticket import (
    TicketBatchCreate,
    TicketBatchRead,
    TicketCreate,
    TicketList,
    TicketRead,
    TicketStatusUpdate,
    TicketAssignmentUpdate,
    ClassificationCorrection,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post(
    "",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def create_ticket(payload: TicketCreate, service: TicketServiceDep) -> TicketRead:
    ticket = await service.create(payload)
    return TicketRead.model_validate(ticket)


@router.post(
    "/batch",
    response_model=TicketBatchRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def create_ticket_batch(
    payload: TicketBatchCreate, service: TicketServiceDep
) -> TicketBatchRead:
    tickets, group_id = await service.create_batch(payload.tickets)
    return TicketBatchRead(
        items=[TicketRead.model_validate(ticket) for ticket in tickets],
        count=len(tickets),
        task_group_id=group_id,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketRead,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def get_ticket(ticket_id: uuid.UUID, service: TicketServiceDep) -> TicketRead:
    ticket = await service.get(ticket_id)
    return TicketRead.model_validate(ticket)


@router.get(
    "",
    response_model=TicketList,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def list_tickets(
    service: TicketServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketList:
    tickets, total = await service.list(limit=limit, offset=offset)
    return TicketList(
        items=[TicketRead.model_validate(ticket) for ticket in tickets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{ticket_id}/status", response_model=TicketRead)
async def update_ticket_status(ticket_id: uuid.UUID, payload: TicketStatusUpdate, service: TicketServiceDep) -> TicketRead:
    return TicketRead.model_validate(await service.update_status(ticket_id, payload.status))


@router.patch("/{ticket_id}/classification", response_model=TicketRead)
async def correct_ticket_classification(ticket_id: uuid.UUID, payload: ClassificationCorrection, service: TicketServiceDep) -> TicketRead:
    return TicketRead.model_validate(await service.correct_classification(ticket_id, payload))


@router.patch("/{ticket_id}/assign", response_model=TicketRead)
async def assign_ticket(ticket_id: uuid.UUID, payload: TicketAssignmentUpdate, service: TicketServiceDep) -> TicketRead:
    return TicketRead.model_validate(await service.assign(ticket_id, payload.assigned_agent_id))
