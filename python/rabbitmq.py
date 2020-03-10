import asyncio
from abc import ABC

import aiopg
import psycopg2
import sqlalchemy as sa
import tornado.ioloop
import tornado.web
from aio_pika import connect_robust, Message
from tornado.options import define, options

metadata = sa.MetaData()

reports = sa.Table('reports', metadata,
                   sa.Column('id', sa.Integer, primary_key=True),
                   sa.Column('report', sa.String(1024)),
                   sa.Column('published', sa.DateTime))

define("port", default=8888, help="run on the given port", type=int)
define("db_port", default=5432, help=" database port")
define("db_host", default="db", help=" database host")
define("db_database", default="postgres", help=" database name")
define("db_user", default="postgres", help=" database user")
define("db_password", default="postgres", help=" database password")

tornado.ioloop.IOLoop.configure('tornado.platform.asyncio.AsyncIOLoop')
io_loop = tornado.ioloop.IOLoop.current()
asyncio.set_event_loop(io_loop.asyncio_loop)

QUEUE = asyncio.Queue()

db_engine = sa.create_engine('postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(
    host=options.db_host,
    port=options.db_port,
    user=options.db_user,
    password=options.db_password,
    dbname=options.db_database
))


class HomeHandler(tornado.web.RequestHandler, ABC):
    async def get(self, slug=None):
        self.write('GET - Home {}'.format(slug))


class SubscriberHandler(tornado.web.RequestHandler, ABC):
    async def get(self):
        message = await QUEUE.get()

        with db_engine.connect() as conn:
            conn.execute(reports.insert().values(report=bytes(message.body).decode("utf-8")))

        await self.finish(message.body)


class PublisherHandler(tornado.web.RequestHandler, ABC):
    async def post(self):
        connection = self.application.amqp_connection
        channel = await connection.channel()

        try:
            await channel.default_exchange.publish(
                Message(body=self.request.body, content_encoding='utf-8'),
                routing_key="test",
            )
        finally:
            await channel.close()

        await self.finish("OK")


class Application(tornado.web.Application):
    def __init__(self, db, amqp_connection):
        self.db = db
        self.amqp_connection = amqp_connection

        api = '/api/v1/device/<id:int>/reports'
        handlers = [
            (r"/publish", PublisherHandler),
            (r"/subscribe", SubscriberHandler),
            (r"/api/v1/device/([^/]+)/reports", HomeHandler),
        ]
        settings = dict(
            debug=True
        )
        super().__init__(handlers, **settings)


async def maybe_create_tables(db):
    try:
        with (await db.cursor()) as cur:
            await cur.execute("SELECT COUNT(*) FROM reports LIMIT 1")
            await cur.fetchone()
    except psycopg2.ProgrammingError:
        with open("migration.sql") as f:
            schema = f.read()
        with (await db.cursor()) as cur:
            await cur.execute(schema)


async def make_app():
    amqp_connection = await connect_robust("amqp://guest:guest@rabbitmq/")

    channel = await amqp_connection.channel()
    queue = await channel.declare_queue('test', auto_delete=True)
    await queue.consume(QUEUE.put, no_ack=True)

    async with aiopg.create_pool(
            host=options.db_host,
            port=options.db_port,
            user=options.db_user,
            password=options.db_password,
            dbname=options.db_database
    ) as db:
        await maybe_create_tables(db)
        return Application(db, amqp_connection)


if __name__ == "__main__":
    app = io_loop.asyncio_loop.run_until_complete(make_app())
    app.listen(options.port)

    tornado.ioloop.IOLoop.current().start()

# curl -H "Content-Type: application/json" -d '{"id": 1}' -X POST 192.168.99.100:8888/publish
# curl -H "Content-Type: application/json" -X GET 192.168.99.100:8888/subscribe | python -m json.tool
