from aiohttp import web
from models import Advertisement, Session, User, engine, init_orm
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

app = web.Application()

async def orm_context(app):
    print("START")
    await init_orm()
    yield
    await engine.dispose()
    print("FINISH")

@web.middleware
async def session_middleware(request: web.Request, handler):
    async with Session() as session:
        request.session = session
        response = await handler(request)
        return response
    
app.cleanup_ctx.append(orm_context)
app.middlewares.append(session_middleware)

def get_http_error(error_cls, msg: str | dict | list):
    return error_cls(
        text=json.dumps(
            {"error": msg},
            ensure_ascii=False  
        ),
        content_type="application/json",
    )

async def get_advertisement(advertisement_id: int, session: AsyncSession) -> Advertisement:
    advertisement = await session.get(Advertisement, advertisement_id)
    if advertisement is None:
        raise get_http_error(web.HTTPNotFound, "Объявление не найдено")
    return advertisement

async def get_user(user_id: int, session: AsyncSession) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise get_http_error(web.HTTPNotFound, "Пользователь не найден")
    return user

async def add_advertisement(advertisement: Advertisement, session: AsyncSession) -> Advertisement:
    session.add(advertisement)
    try:
        await session.commit()
    except IntegrityError:
        raise get_http_error(web.HTTPConflict, "Объявление уже существует")
    return advertisement

async def add_user_handler(request: web.Request) -> web.Response:
    session: AsyncSession = request.session
    user_data = await request.json()

    username = user_data.get("name")
    if not username:
        raise get_http_error(web.HTTPBadRequest, "Поле 'name' отсутствует")

    user = User(name=username)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        raise get_http_error(web.HTTPConflict, "Пользователь уже существует")

    return web.json_response({"id": user.id})

class AdvertisementView(web.View):
    
    @property
    def advertisement_id(self):
        return int(self.request.match_info["advertisement_id"])
    
    @property
    def session(self) -> AsyncSession:
        return self.request.session
    
    async def get(self):
        advertisement = await get_advertisement(self.advertisement_id, self.session)
        return web.Response(text=json.dumps(advertisement.dict, ensure_ascii=False), content_type="application/json")

    async def post(self):
        advertisement_data = await self.request.json()
        title = advertisement_data.get('title')
        description = advertisement_data.get('description')
        owner_id = advertisement_data.get("owner_id")

        if not title or not description or not owner_id:
            raise get_http_error(web.HTTPBadRequest, "Пропущенное поле")

        user = await get_user(owner_id, self.session)

        advertisement = Advertisement(**advertisement_data)
        advertisement = await add_advertisement(advertisement, self.session)

        return web.Response(text=json.dumps({
            "id": advertisement.id,
            "title": advertisement.title,
            "description": advertisement.description,
            "created_at": advertisement.created_at.isoformat(),
            "owner_id": advertisement.owner_id
        }, ensure_ascii=False), content_type="application/json", status=201)

    async def patch(self):
        advertisement_data = await self.request.json()
        advertisement = await get_advertisement(self.advertisement_id, self.session)
        for field, value in advertisement_data.items():
            setattr(advertisement, field, value)
        advertisement = await add_advertisement(advertisement, self.session)
        await self.session.commit()

        return web.Response(text=json.dumps({
            "id": advertisement.id,
            "title": advertisement.title,
            "description": advertisement.description,
            "created_at": advertisement.created_at.isoformat(),
            "owner_id": advertisement.owner_id
        }, ensure_ascii=False), content_type="application/json", status=200)

    async def delete(self):
        advertisement = await get_advertisement(self.advertisement_id, self.session)
        await self.session.delete(advertisement)
        await self.session.commit()
        return web.Response(text=json.dumps({"status": "Удалено"}, ensure_ascii=False), content_type="application/json")

app.add_routes(
    [
        web.post("/ads/", AdvertisementView),
        web.get(r"/ads/{advertisement_id:\d+}/", AdvertisementView),
        web.patch(r"/ads/{advertisement_id:\d+}/", AdvertisementView),
        web.delete(r"/ads/{advertisement_id:\d+}/", AdvertisementView),
        web.post("/add_user", add_user_handler),  
    ]
)

if __name__ == '__main__':
    web.run_app(app)
