import base64
from io import BytesIO
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from reportlab.pdfgen import canvas
from .core import bad, fail, identifier, positive_int, read, mutate, sign, utcnow
from .app import body

router=APIRouter()

def receipt_pdf(order_id,total_minor):
    stream=BytesIO()
    page=canvas.Canvas(stream,pagesize=(595,842))
    page.setTitle("NaSCon receipt "+order_id)
    page.setFont("Helvetica-Bold",20)
    page.drawString(50,780,"NaSCon Club Store")
    page.setFont("Helvetica",12)
    page.drawString(50,744,"Order: "+order_id)
    page.drawString(50,722,"Total: PKR %.2f"%(total_minor/100))
    page.drawString(50,700,"Payment status: PAID")
    page.showPage()
    page.save()
    return base64.b64encode(stream.getvalue()).decode("ascii")

def checkout_apply(state,data):
    oid=data.get("order_id");customer=data.get("customer_id")
    items=data.get("items");payment=data.get("payment");discount=data.get("discount_code")
    if not identifier(oid) or not isinstance(customer,str) or not 1<=len(customer)<=64:bad("order_id","customer_id")
    if not isinstance(items,list) or not 1<=len(items)<=10 or any(not isinstance(it,dict) or not identifier(it.get("variant_id")) or not positive_int(it.get("quantity")) or it["quantity"]>10 for it in items):bad("items")
    if len(set(it["variant_id"] for it in items))!=len(items):bad("items")
    if not isinstance(payment,dict) or not isinstance(payment.get("token"),str) or payment["token"] not in ("tok_success","tok_declined","tok_capture_fail"):bad("payment")
    if discount is not None and not isinstance(discount,str):bad("discount_code")
    existing=state["orders"].get(oid)
    if existing is not None:
        if existing["request"]==data:return 200,existing["response"]
        fail(409,"DUPLICATE_ORDER_ID")
    for item in items:
        if item["variant_id"] not in state["inventory"]:fail(404,"VARIANT_NOT_FOUND",variant_id=item["variant_id"])
    if discount not in (None,"WELCOME10"):fail(400,"INVALID_DISCOUNT_CODE")
    for item in items:
        if state["inventory"][item["variant_id"]]["stock"]<item["quantity"]:fail(409,"OUT_OF_STOCK",variant_id=item["variant_id"])
    if payment["token"]=="tok_declined":fail(402,"PAYMENT_DECLINED")
    if payment["token"]=="tok_capture_fail":fail(402,"PAYMENT_CAPTURE_FAILED")
    receipt_items=[]
    for it in items:
        variant=state["inventory"][it["variant_id"]]
        receipt_items.append({"variant_id":it["variant_id"],"quantity":it["quantity"],"unit_price_minor":variant["price_minor"]})
        variant["stock"]-=it["quantity"]
    subtotal=sum(it["quantity"]*it["unit_price_minor"] for it in receipt_items)
    saved=subtotal//10 if discount=="WELCOME10" else 0
    total=subtotal-saved
    payload={"order_id":oid,"customer_id":customer,"items":receipt_items,"subtotal_minor":subtotal,"discount_minor":saved,"total_minor":total,"currency":"PKR","paid_at":utcnow()}
    state["auth_serial"]=state.get("auth_serial",0)+1
    counter=state["auth_serial"]
    resp={"order_id":oid,"status":"paid","currency":"PKR","items":receipt_items,"subtotal_minor":subtotal,"discount_minor":saved,"total_minor":total,"payment":{"authorization_id":"auth_%d"%counter,"capture_id":"cap_%d"%counter,"state":"captured"},"receipt":{"payload":payload,"signature":sign(oid,payload),"pdf_base64":receipt_pdf(oid,total)}}
    state["orders"][oid]={"request":data,"response":resp}
    return 201,resp

@router.post("/audit/v1/checkout")
async def checkout(req:Request):
    d=await body(req)
    code,res=mutate(lambda s:checkout_apply(s,d))
    if code==201:publish_order(res["order_id"])
    return JSONResponse(status_code=code,content=res)


def publish_order(order_id):
    try:
        import redis,os
        redis.Redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"),socket_timeout=.2).xadd("nascon:events",{"type":"order.paid","order_id":order_id})
    except Exception:pass

@router.get("/audit/v1/inventory/{variant_id}")
def inventory(variant_id:str):
    def get(s):
        v=s["inventory"].get(variant_id)
        if v is None:fail(404,"VARIANT_NOT_FOUND")
        return {"variant_id":variant_id,"stock":v["stock"],"reserved":v["reserved"]}
    return read(get)
