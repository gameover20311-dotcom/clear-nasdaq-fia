import {NextResponse} from "next/server";
export async function GET(){try{const r=await fetch("http://127.0.0.1:8001/api/phase34",{cache:"no-store"});return NextResponse.json(await r.json(),{status:r.status})}catch(e){return NextResponse.json({ok:false,error:String(e)},{status:503})}}
