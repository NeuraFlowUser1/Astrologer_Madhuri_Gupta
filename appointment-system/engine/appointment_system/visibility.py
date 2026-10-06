"""Website guard with fresh signed reads; ordinary site and enquiries do not depend on Neon."""
import re
from fastapi.responses import JSONResponse
from .service_control import ControlError
from .surfaces import classify

HEADERS={"Cache-Control":"private, no-store","Referrer-Policy":"no-referrer",
         "X-Content-Type-Options":"nosniff","X-Robots-Tag":"noindex, nofollow"}


class BookingVisibility:
    def __init__(self,app,reader):
        self.app=app;self.reader=reader

    async def __call__(self,scope,receive,send):
        if scope["type"]!="http":return await self.app(scope,receive,send)
        path=scope["path"];kind=classify(path)
        state_path=path in ("/api/service-state","/api/service-state/probe")
        if kind=="invalid":
            return await JSONResponse({"code":"invalid_address"},400,headers=HEADERS)(scope,receive,send)
        if kind!="booking" and not state_path:
            return await self.app(scope,receive,send)
        if state_path and scope["method"] not in ("GET","HEAD"):
            return await JSONResponse({"code":"method_not_allowed"},405,headers=HEADERS)(scope,receive,send)
        try:
            if self.reader is None:raise ControlError("projection_configuration")
            if path=="/api/service-state/probe":
                nonces=[value.decode("ascii") for name,value in scope["headers"] if name.lower()==b"x-booking-state-nonce"]
                if len(nonces)!=1 or not re.fullmatch(r"[a-f0-9]{64}",nonces[0]):
                    return await JSONResponse({"code":"invalid_probe"},400,headers=HEADERS)(scope,receive,send)
                attested=await self.reader.attestation(nonces[0])
                return await JSONResponse(attested,headers=HEADERS)(scope,receive,send)
            state=await self.reader.read()
        except (ControlError,UnicodeError):
            code,status=("booking_unavailable",404) if kind=="booking" else ("state_unavailable",503)
            return await JSONResponse({"code":code,"enabled":False},status,headers=HEADERS)(scope,receive,send)
        if state_path:
            return await JSONResponse({"enabled":state["enabled"],"activation_epoch":state["activation_epoch"]},headers=HEADERS)(scope,receive,send)
        if state["enabled"] is not True:
            return await JSONResponse({"code":"page_unavailable"},404,headers=HEADERS)(scope,receive,send)
        scope.setdefault("state",{})["booking_activation_epoch"]=state["activation_epoch"]
        denied=False
        async def current_send(message):
            nonlocal denied
            if denied:return
            if message["type"]=="http.response.start":
                # A request may have committed before OFF, but its public
                # booking response must not escape after that transition.
                try:
                    latest=await self.reader.read()
                    visible=latest["enabled"] is True and latest["activation_epoch"]==state["activation_epoch"]
                except (ControlError,UnicodeError):visible=False
                if not visible:
                    denied=True
                    return await JSONResponse({"code":"page_unavailable"},404,headers=HEADERS)(scope,receive,send)
            await send(message)
        return await self.app(scope,receive,current_send)
