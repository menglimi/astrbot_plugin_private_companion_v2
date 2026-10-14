"""Authenticated private-window review of retained proactive screen originals."""

from astrbot.api.web import request

from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.screen.review import ScreenObservationReview

from .management_identity import dashboard_operator


class ScreenObservationWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self, prefix):
        return [(prefix + "/last-observation", self.latest, ["GET"], "Review last proactive Screen capture"),
                (prefix + "/last-original", self.original, ["GET"], "Read retained proactive Screen original")]

    async def _run(self, *, original=False):
        from .web_api import outcome_response
        try:
            username = request.username
            if type(username) is not str or not username.strip() or username.startswith("api_key:"):
                raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
            query = request.query
            expected = {"capture_id"} if original else set()
            if set(query.keys()) != expected or any(len(query.getlist(key)) != 1 for key in query.keys()):
                raise TaskError("screen_access_request_invalid", "unknown or repeated screen review query fields")
            capture_id = query.get("capture_id") if original else None
            if original and (type(capture_id) is not str or not capture_id or len(capture_id) > 128):
                raise TaskError("screen_access_request_invalid", "select the displayed retained capture")
            controller = self.controller
            async with controller._control_lock:
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "the V2 host has stopped")
                session = controller.session or controller.last_session
                if session is None or controller.runtime is None:
                    raise TaskError("staging_not_initialized", "load the configured V2 profile")
                at = controller.now()
                operator = dashboard_operator(controller.runtime, username, at=at)
                service = ScreenObservationReview(session.application, session.profile.target)
                result = service.original(operator, at, capture_id) if original else service.latest(operator, at)
                return outcome_response(Outcome.success(result))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, OSError):
            return outcome_response(Outcome.failed("screen_original_unavailable", "the saved screen record is unavailable"))

    async def latest(self):
        return await self._run()

    async def original(self):
        return await self._run(original=True)
