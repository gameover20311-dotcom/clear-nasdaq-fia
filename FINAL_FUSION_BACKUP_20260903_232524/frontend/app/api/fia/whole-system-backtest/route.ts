import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET(){
  try{
    const r=await fetch("http://127.0.0.1:8001/api/backtest/whole-system/report",{cache:"no-store"});
    const text=await r.text();
    return new NextResponse(text,{status:r.status,headers:{"content-type":"application/json","cache-control":"no-store"}});
  }catch(e){
    return NextResponse.json({ok:false,state:"BACKEND_UNAVAILABLE",error:String(e)},{status:503});
  }
}
