#!/usr/bin/env python3

import queue
import logging
from dbus_next.service import ServiceInterface, method
from dbus_next.aio import MessageBus

from orgfoundrysync import commands

logger = logging.getLogger("dbus")
logger.setLevel(logging.INFO)


class OrgFoundrySyncInterface(ServiceInterface):
    def __init__(self, name: str, work_queue: queue.Queue):
        super().__init__(name)
        self.work_queue = work_queue

    @method()
    def UploadNote(self, path: "s") -> "":
        logger.info(f"Uploading note {path}")
        self.work_queue.put(commands.UploadNote(path=path))

    @method()
    def UploadAllNotes(self) -> "":
        logger.info(f"Uploading all notes")
        self.work_queue.put(commands.UploadAllNotes())

    @method()
    def DownloadNote(self, name: "s") -> "":
        logger.info(f"Downloading note {name}")
        self.work_queue.put(commands.DownloadNote(name=name))

    @method()
    def DownloadNotes(self) -> "":
        logger.info(f"Downloading all notes")
        self.work_queue.put(commands.DownloadAllNotes())


async def start_server(queue: queue.Queue):
    bus = await MessageBus().connect()
    interface = OrgFoundrySyncInterface("com.foundry.OrgFoundrySync", queue)
    bus.export("/com/foundry/orgfoundrysync", interface)
    await bus.request_name("com.foundry.OrgFoundrySync")
    logger.info("Started server and registered Service.")
    return bus
