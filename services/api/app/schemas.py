from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.vocabulary import Category, MissingInfo, Priority, Role, TicketStatus

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text4000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
# Büyük harf girilebilir; desen kontrolünden sonra küçük harfe çevrilir.
Username = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9._-]{3,50}$")
]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Kullanıcı ve ekip ---


class TeamOut(ORM):
    id: UUID
    code: str
    name: str


class PersonOut(ORM):
    """Başkalarına gösterilen asgari kişi bilgisi (kullanıcı adı ve ekipler yok)."""

    id: UUID
    display_name: str
    role: Role


class UserOut(ORM):
    id: UUID
    username: str
    display_name: str
    role: Role
    is_active: bool
    teams: list[TeamOut]


class LoginRequest(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=50)]
    password: Annotated[str, StringConstraints(max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TeamWithMembers(TeamOut):
    members: list[PersonOut]


class UserCreate(BaseModel):
    username: Username
    display_name: Text200
    password: Password
    role: Role = Role.REQUESTER


class UserPatch(BaseModel):
    display_name: Text200 | None = None
    role: Role | None = None
    is_active: bool | None = None


# --- Talep ---


class TicketCreate(BaseModel):
    title: Text200
    description: Text4000
    location: Text200


class EventOut(ORM):
    id: int
    kind: str
    data: dict[str, Any]
    created_at: datetime
    actor: PersonOut | None


class TicketSummary(ORM):
    id: UUID
    number: int
    title: str
    location: str
    status: TicketStatus
    category: Category | None
    priority: Priority
    team: TeamOut | None
    assignee: PersonOut | None
    created_by: PersonOut
    missing_info: list[str]
    review_required: bool
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketSummary):
    description: str
    # Bu kullanıcının bu talepte yapabileceği işlemler (sunucu hesaplar, istemci yalnızca gösterir).
    allowed_transitions: list[TicketStatus]
    can_assign: bool
    can_edit: bool
    events: list[EventOut]


class TicketList(BaseModel):
    items: list[TicketSummary]
    total: int
    limit: int
    offset: int


class TransitionRequest(BaseModel):
    to: TicketStatus
    note: Note | None = None


class AssignRequest(BaseModel):
    team_id: UUID
    assignee_id: UUID | None = None
    note: Note | None = None


class TicketPatch(BaseModel):
    """Yönetici düzeltmesi. Gönderilmeyen alan değişmez; category için null göndermek temizler."""

    priority: Priority | None = None
    category: Category | None = None
    missing_info: list[MissingInfo] | None = Field(default=None, max_length=len(MissingInfo))
    note: Note | None = None


# --- Sözlük ---


class LabeledValue(BaseModel):
    code: str
    label: str


class Vocabulary(BaseModel):
    roles: list[LabeledValue]
    statuses: list[LabeledValue]
    priorities: list[LabeledValue]
    categories: list[LabeledValue]
    missing_info: list[LabeledValue]
    # Kategori → varsayılan ekip kodu
    category_default_team: dict[str, str]
