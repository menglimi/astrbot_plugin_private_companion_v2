"""Reality camera observation has its own private-scope consent record."""

from .reality_access import RealitySnapshotAccess


ACTION = "reality.camera.observe"


class RealityCameraAccess(RealitySnapshotAccess):
    def __init__(self, application, context, package):
        super().__init__(application, context, package, capability=ACTION)


__all__ = ["ACTION", "RealityCameraAccess"]
