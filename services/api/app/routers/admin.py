from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.deps import AdminUser, DbSession, require_admin
from app.schemas import TeamWithMembers, UserCreate, UserOut, UserPatch
from app.services import accounts

router = APIRouter(prefix="/admin", tags=["yönetim"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[UserOut], summary="Kullanıcılar")
def list_users(db: DbSession) -> list[UserOut]:
    return [UserOut.model_validate(user) for user in accounts.list_users(db)]


@router.post("/users", response_model=UserOut, status_code=201, summary="Kullanıcı oluştur")
def create_user(data: UserCreate, db: DbSession) -> UserOut:
    return UserOut.model_validate(accounts.create_user(db, data))


@router.patch("/users/{user_id}", response_model=UserOut, summary="Kullanıcıyı güncelle")
def patch_user(user_id: UUID, data: UserPatch, admin: AdminUser, db: DbSession) -> UserOut:
    return UserOut.model_validate(accounts.patch_user(db, admin, user_id, data))


@router.get("/teams", response_model=list[TeamWithMembers], summary="Ekipler ve üyeleri")
def list_teams(db: DbSession) -> list[TeamWithMembers]:
    return [TeamWithMembers.model_validate(team) for team in accounts.list_teams(db)]


@router.put(
    "/teams/{team_id}/members/{user_id}", status_code=204, summary="Teknik görevliyi ekibe ekle"
)
def add_member(team_id: UUID, user_id: UUID, db: DbSession) -> Response:
    accounts.add_member(db, team_id, user_id)
    return Response(status_code=204)


@router.delete(
    "/teams/{team_id}/members/{user_id}", status_code=204, summary="Görevliyi ekipten çıkar"
)
def remove_member(team_id: UUID, user_id: UUID, db: DbSession) -> Response:
    accounts.remove_member(db, team_id, user_id)
    return Response(status_code=204)
