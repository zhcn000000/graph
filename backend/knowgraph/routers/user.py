from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from knowgraph.database.user import TokenDataDict, UserManager

router = APIRouter()
auth_router = APIRouter()
user_manager = UserManager()

CurrentUserDep = Depends(UserManager.get_current_user)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: UUID
    username: str


class UserListResponse(BaseModel):
    users: list[UserResponse]


class StatusResponse(BaseModel):
    success: bool
    status: str


class UpdateUserRequest(BaseModel):
    username: str | None = None
    password: str | None = None


@auth_router.post("/login")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenResponse:
    token = await user_manager.averify_credentials(form_data.username, form_data.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return TokenResponse(access_token=token)


@auth_router.post("/register")
async def register(request: RegisterRequest) -> StatusResponse:
    try:
        await user_manager.ainsert(request.username, request.password)
    except Exception as e:
        raise HTTPException(status_code=409, detail="Username already exists") from e
    return StatusResponse(success=True, status="用户注册成功")


@auth_router.post("/refresh")
async def refresh_token(
    token_data: Annotated[TokenDataDict, CurrentUserDep],
) -> TokenResponse:
    token = await user_manager.acreate_access_token(token_data["username"])
    return TokenResponse(access_token=token)


@router.get("/me")
async def get_current_user(
    token_data: Annotated[TokenDataDict, CurrentUserDep],
) -> UserResponse:
    user_info = await user_manager.aget(token_data["user_id"])
    if user_info is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(id=user_info["id"], username=user_info["username"])


@router.get("/")
async def list_users(
    token_data: Annotated[TokenDataDict, CurrentUserDep],
) -> UserListResponse:
    users = await user_manager.alists()
    return UserListResponse(users=[UserResponse(id=v["id"], username=v["username"]) for v in users.values()])


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    token_data: Annotated[TokenDataDict, CurrentUserDep],
) -> StatusResponse:
    await user_manager.adelete(user_id)
    return StatusResponse(success=True, status="用户删除成功")


@router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    token_data: Annotated[TokenDataDict, CurrentUserDep],
) -> StatusResponse:
    await user_manager.aupdate(user_id, username=request.username, password=request.password)
    return StatusResponse(success=True, status="用户更新成功")
