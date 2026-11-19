// Fetch forbids a body, even an empty string, on no-content responses.
export async function forwardBackendResponse(result){
 const body=[204,205,304].includes(result.status)?null:await result.text();
 return new Response(body,{status:result.status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
}
