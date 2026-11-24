import os, sqlite3, io
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

DB = os.getenv("DATABASE_PATH", "/data/wz.sqlite3")
Path(DB).parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="WZ – dokumenty magazynowe")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS recipients(
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, nip TEXT DEFAULT '',
          address TEXT DEFAULT '', city TEXT DEFAULT '', notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS materials(
          id INTEGER PRIMARY KEY, index_no TEXT DEFAULT '', name TEXT NOT NULL,
          unit TEXT DEFAULT 'szt.', default_price REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS documents(
          id INTEGER PRIMARY KEY, number TEXT UNIQUE NOT NULL, year INTEGER NOT NULL,
          sequence INTEGER NOT NULL, recipient_id INTEGER, recipient_name TEXT NOT NULL,
          recipient_nip TEXT DEFAULT '', recipient_address TEXT DEFAULT '',
          issue_date TEXT NOT NULL, warehouse_no TEXT DEFAULT '', transport TEXT DEFAULT '',
          order_no TEXT DEFAULT '', purpose TEXT DEFAULT '', dispatch_date TEXT DEFAULT '',
          shipping_cost TEXT DEFAULT '', invoice_ref TEXT DEFAULT '',
          issuer TEXT DEFAULT '', approver TEXT DEFAULT '', notes TEXT DEFAULT '',
          created_at TEXT NOT NULL,
          FOREIGN KEY(recipient_id) REFERENCES recipients(id)
        );
        CREATE TABLE IF NOT EXISTS document_items(
          id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
          index_no TEXT DEFAULT '', name TEXT NOT NULL, quantity_planned REAL DEFAULT 0,
          unit TEXT DEFAULT 'szt.', quantity_issued REAL DEFAULT 0,
          price REAL DEFAULT 0, account_no TEXT DEFAULT '', stock_qty TEXT DEFAULT '',
          FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_documents_date ON documents(issue_date);
        CREATE INDEX IF NOT EXISTS idx_documents_recipient ON documents(recipient_name);
        """)
init_db()

class Recipient(BaseModel):
    name: str
    nip: str = ""
    address: str = ""
    city: str = ""
    notes: str = ""

class Material(BaseModel):
    index_no: str = ""
    name: str
    unit: str = "szt."
    default_price: float = 0

class Item(BaseModel):
    index_no: str = ""
    name: str
    quantity_planned: float = 0
    unit: str = "szt."
    quantity_issued: float = 0
    price: float = 0
    account_no: str = ""
    stock_qty: str = ""

class Document(BaseModel):
    recipient_id: Optional[int] = None
    recipient_name: str
    recipient_nip: str = ""
    recipient_address: str = ""
    issue_date: str = Field(default_factory=lambda: date.today().isoformat())
    warehouse_no: str = ""
    transport: str = ""
    order_no: str = ""
    purpose: str = ""
    dispatch_date: str = ""
    shipping_cost: str = ""
    invoice_ref: str = ""
    issuer: str = ""
    approver: str = ""
    notes: str = ""
    items: list[Item] = []

@app.get("/", response_class=HTMLResponse)
def home():
    return Path("app/static/index.html").read_text(encoding="utf-8")

@app.get("/api/recipients")
def recipients():
    with conn() as c:
        return [dict(x) for x in c.execute("SELECT * FROM recipients ORDER BY name")]
@app.post("/api/recipients")
def add_recipient(x: Recipient):
    with conn() as c:
        cur=c.execute("INSERT INTO recipients(name,nip,address,city,notes) VALUES(?,?,?,?,?)",
                      (x.name,x.nip,x.address,x.city,x.notes))
        return {"id":cur.lastrowid}
@app.delete("/api/recipients/{rid}")
def delete_recipient(rid:int):
    with conn() as c: c.execute("DELETE FROM recipients WHERE id=?",(rid,))
    return {"ok":True}

@app.get("/api/materials")
def materials():
    with conn() as c: return [dict(x) for x in c.execute("SELECT * FROM materials ORDER BY name")]
@app.post("/api/materials")
def add_material(x: Material):
    with conn() as c:
        cur=c.execute("INSERT INTO materials(index_no,name,unit,default_price) VALUES(?,?,?,?)",
                      (x.index_no,x.name,x.unit,x.default_price))
        return {"id":cur.lastrowid}
@app.delete("/api/materials/{mid}")
def delete_material(mid:int):
    with conn() as c: c.execute("DELETE FROM materials WHERE id=?",(mid,))
    return {"ok":True}

@app.post("/api/documents")
def create_document(x: Document):
    if not x.items: raise HTTPException(400,"Dokument musi zawierać przynajmniej jedną pozycję.")
    try: yr=int(x.issue_date[:4])
    except: raise HTTPException(400,"Nieprawidłowa data dokumentu.")
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        seq=c.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM documents WHERE year=?",(yr,)).fetchone()[0]
        number=f"WZ/{seq:03d}/{yr}"
        cur=c.execute("""INSERT INTO documents(number,year,sequence,recipient_id,recipient_name,recipient_nip,
          recipient_address,issue_date,warehouse_no,transport,order_no,purpose,dispatch_date,shipping_cost,
          invoice_ref,issuer,approver,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (number,yr,seq,x.recipient_id,x.recipient_name,x.recipient_nip,x.recipient_address,x.issue_date,
           x.warehouse_no,x.transport,x.order_no,x.purpose,x.dispatch_date,x.shipping_cost,x.invoice_ref,
           x.issuer,x.approver,x.notes,datetime.now().isoformat(timespec="seconds")))
        did=cur.lastrowid
        for it in x.items:
            c.execute("""INSERT INTO document_items(document_id,index_no,name,quantity_planned,unit,
              quantity_issued,price,account_no,stock_qty) VALUES(?,?,?,?,?,?,?,?,?)""",
              (did,it.index_no,it.name,it.quantity_planned,it.unit,it.quantity_issued,it.price,it.account_no,it.stock_qty))
        return {"id":did,"number":number}

@app.put("/api/documents/{did}")
def update_document(did: int, x: Document):
    if not x.items:
        raise HTTPException(400, "Dokument musi zawierać przynajmniej jedną pozycję.")
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        old = c.execute("SELECT id FROM documents WHERE id=?", (did,)).fetchone()
        if not old:
            raise HTTPException(404, "Nie znaleziono dokumentu")
        c.execute("""UPDATE documents SET recipient_id=?,recipient_name=?,recipient_nip=?,recipient_address=?,
          issue_date=?,warehouse_no=?,transport=?,order_no=?,purpose=?,dispatch_date=?,shipping_cost=?,
          invoice_ref=?,issuer=?,approver=?,notes=? WHERE id=?""",
          (x.recipient_id,x.recipient_name,x.recipient_nip,x.recipient_address,x.issue_date,x.warehouse_no,
           x.transport,x.order_no,x.purpose,x.dispatch_date,x.shipping_cost,x.invoice_ref,x.issuer,x.approver,x.notes,did))
        c.execute("DELETE FROM document_items WHERE document_id=?", (did,))
        for it in x.items:
            c.execute("""INSERT INTO document_items(document_id,index_no,name,quantity_planned,unit,
              quantity_issued,price,account_no,stock_qty) VALUES(?,?,?,?,?,?,?,?,?)""",
              (did,it.index_no,it.name,it.quantity_planned,it.unit,it.quantity_issued,it.price,it.account_no,it.stock_qty))
    return {"id": did, "updated": True}

@app.get("/api/documents")
def list_documents(q:str="", date_from:str="", date_to:str=""):
    sql="SELECT * FROM documents WHERE 1=1"; args=[]
    if q:
        sql+=" AND (number LIKE ? OR recipient_name LIKE ?)"; args += [f"%{q}%",f"%{q}%"]
    if date_from: sql+=" AND issue_date>=?"; args.append(date_from)
    if date_to: sql+=" AND issue_date<=?"; args.append(date_to)
    sql+=" ORDER BY issue_date DESC, id DESC"
    with conn() as c: return [dict(x) for x in c.execute(sql,args)]

@app.get("/api/documents/{did}")
def get_document(did:int):
    with conn() as c:
        d=c.execute("SELECT * FROM documents WHERE id=?",(did,)).fetchone()
        if not d: raise HTTPException(404,"Nie znaleziono dokumentu")
        out=dict(d); out["items"]=[dict(x) for x in c.execute("SELECT * FROM document_items WHERE document_id=? ORDER BY id",(did,))]
        return out

def money(v):
    return f"{float(v or 0):.2f}".replace(".", ",")

def draw_fit(c, text, x, y, maxw, size=7):
    text=str(text or "")
    while size>5 and stringWidth(text,"Helvetica",size)>maxw: size-=0.3
    c.setFont("Helvetica",size); c.drawString(x,y,text)

def draw_form(c, d, items, top, copy=False):
    # Formularz WZ w układzie zgodnym z dostarczonym wzorem: nagłówek, pozycje i podpisy.
    left=42; right=553; width=right-left
    h=top
    c.setLineWidth(.55); c.setFont("Helvetica",6)
    # header frame
    c.rect(left,h-68,width,68)
    c.line(left+250,h,left+250,h-68); c.line(left+365,h,left+365,h-68)
    c.setFont("Helvetica-Bold",14); c.drawCentredString(left+307,h-28,"WZ")
    c.setFont("Helvetica",7); c.drawCentredString(left+307,h-40,"Wydanie materiałów")
    c.drawCentredString(left+307,h-50,"na zewnątrz")
    c.setFont("Helvetica",6)
    c.drawString(left+5,h-10,"Oryginał" if not copy else "Kopia")
    c.drawString(left+255,h-10,"Odbiorca")
    c.drawString(left+370,h-10,"Nr bieżący")
    c.drawString(left+370,h-31,"Egz.")
    c.drawString(left+370,h-51,"Nr magazynowy")
    c.drawString(left+370,h-64,"Data wystawienia")
    draw_fit(c,d["recipient_name"],left+255,h-24,105,7)
    draw_fit(c,"NIP: "+d["recipient_nip"],left+5,h-29,235,6)
    draw_fit(c,d["recipient_address"],left+5,h-42,235,6)
    draw_fit(c,d["number"],left+405,h-10,100,7)
    draw_fit(c,"1" if not copy else "2",left+405,h-31,100,7)
    draw_fit(c,d["warehouse_no"],left+405,h-51,100,7)
    draw_fit(c,d["issue_date"],left+435,h-64,70,7)
    # metadata row
    y=h-88
    c.rect(left,y,width,20)
    widths=[100,75,105,75,80,76]
    labels=["Środek transportu","Zamówienie","Przeznaczenie","Data wysyłki","Wysyłka na koszt","Nr i data faktury / spec."]
    vals=[d["transport"],d["order_no"],d["purpose"],d["dispatch_date"],d["shipping_cost"],d["invoice_ref"]]
    xx=left
    for w,l,v in zip(widths,labels,vals):
        c.line(xx,y,xx,y+20); c.setFont("Helvetica",5.3); c.drawString(xx+3,y+13,l)
        draw_fit(c,v,xx+3,y+3,w-6,6); xx+=w
    c.line(right,y,right,y+20)
    # item table
    y2=y-18
    col=[42,93,203,265,291,348,406,462,515,553]
    headers=["Nr indeksu","Nazwa materiału / wyrobu / opakowania","Ilość zadysponowana","j.m.","Wydana","Cena (zł/gr)","Wartość (zł/gr)","Konto syntet. mater.","Zapas ilość"]
    c.rect(left,y2-176,width,176)
    for x in col[1:-1]: c.line(x,y2,x,y2-176)
    c.line(left,y2-18,right,y2-18)
    for x,lab in zip(col[:-1],headers):
        draw_fit(c,lab,x+2,y2-12,col[col.index(x)+1]-x-4,5.2)
    rows=max(1,min(len(items),9)); rowh=17
    for i,it in enumerate(items[:9]):
        yy=y2-31-i*rowh
        vals=[it["index_no"],it["name"],money(it["quantity_planned"]),it["unit"],money(it["quantity_issued"]),money(it["price"]),money(it["quantity_issued"]*it["price"]),it["account_no"],it["stock_qty"]]
        for j,v in enumerate(vals): draw_fit(c,v,col[j]+2,yy,col[j+1]-col[j]-4,6)
        if i<len(items)-1: c.setLineWidth(.2); c.line(left,yy-5,right,yy-5); c.setLineWidth(.55)
    # footer
    fy=y2-195
    c.rect(left,fy,width,19)
    c.line(left+80,fy,left+80,fy+19); c.line(left+150,fy,left+150,fy+19)
    c.line(left+300,fy,left+300,fy+19); c.line(left+375,fy,left+375,fy+19)
    c.setFont("Helvetica",6)
    c.drawString(left+3,fy+12,"Wystawił")
    draw_fit(c,d["issuer"],left+3,fy+3,74,6)
    c.drawString(left+83,fy+12,"Zatwierdził")
    draw_fit(c,d["approver"],left+83,fy+3,64,6)
    c.drawString(left+154,fy+12,"Wydał / Data")
    c.drawString(left+304,fy+12,"Odebrał")
    c.setFont("Helvetica",5.5); c.drawString(left+380,fy+12,"Ewidencja ilościowo-wartościowa")
    c.drawString(left+3,fy-8,"WZ wydania materiałów na zewnątrz")

def make_pdf(d, items):
    buf=io.BytesIO(); c=canvas.Canvas(buf,pagesize=A4)
    c.setTitle(d["number"])
    draw_form(c,d,items,790,False)
    draw_form(c,d,items,390,True)
    c.showPage(); c.save(); buf.seek(0); return buf

@app.get("/api/documents/{did}/pdf")
def document_pdf(did:int):
    d=get_document(did); buf=make_pdf(d,d["items"])
    safe=d["number"].replace("/","-")
    return StreamingResponse(buf,media_type="application/pdf",
      headers={"Content-Disposition":f'inline; filename="{safe}.pdf"'})
