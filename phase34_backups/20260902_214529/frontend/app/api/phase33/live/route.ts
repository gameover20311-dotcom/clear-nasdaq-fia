export const dynamic = "force-dynamic";
export async function GET() {
  try { const r=await fetch("http://127.0.0.1:8001/api/phase33",{cache:"no-store"}); return Response.json(await r.json(),{status:r.status}); }
  catch(e:any){ return Response.json({ok:false,error:String(e)},{status:502}); }
}
