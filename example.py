import asyncio

from pylgtv import WebOsClient as wok

async def test():
    client = wok('192.168.1.131')
    return await client.power_off()


loop = asyncio.get_event_loop()
task = asyncio.ensure_future(test())
loop.run_until_complete(task)
loop.close()
print(task.result())
