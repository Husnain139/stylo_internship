# FastAPI wrapper around ask_nlp.py.
#   python -m uvicorn api:app --reload --port 8000

from fastapi import FastAPI, HTTPException
'''
-- 4xx Client Error Statuses --
400 Bad Request: The request has invalid syntax or data.
401 Unauthorized: Authentication is required and has failed or not been provided.
402 Payment Required: Reserved for future use (sometimes used for subscription walls).
403 Forbidden: The client is authenticated but does not have permission for this resource.
404 Not Found: The requested resource could not be found.
405 Method Not Allowed: The request method (e.g., POST) is not supported for this URL.
406 Not Acceptable: The resource cannot generate content matching the Accept headers sent.
407 Proxy Authentication Required: The client must first authenticate itself with the proxy.
408 Request Timeout: The server timed out waiting for the request.
409 Conflict: The request conflicts with the current state of the server (e.g., duplicate entries).
410 Gone: The resource is permanently deleted and will not return.
411 Length Required: The request did not specify the length of its content, which is required.
412 Precondition Failed: The server does not meet one of the preconditions specified by the client.
413 Payload Too Large: The request entity is larger than limits defined by the server.
414 URI Too Long: The URL requested by the client is longer than the server is willing to interpret.
415 Unsupported Media Type: The media format of the requested data is not supported.
416 Range Not Satisfiable: The range specified by the Range header in the request cannot be fulfilled.
417 Expectation Failed: The expectation given in the Expect request-header field could not be met.
418 I'm a teapot: A joke/Easter egg code defined in RFC 2324.
421 Misdirected Request: The request was directed at a server that is not able to produce a response.
422 Unprocessable Entity: The request was well-formed but has semantic errors (validation failed).
423 Locked: The resource that is being accessed is locked.
424 Failed Dependency: The request failed due to failure of a previous request.
425 Too Early: The server is unwilling to risk processing a request that might be replayed.
426 Upgrade Required: The client should switch to a different protocol (e.g., TLS/1.3).
428 Precondition Required: The origin server requires the request to be conditional.
429 Too Many Requests: The user has sent too many requests in a given amount of time (rate-limited).
431 Request Header Fields Too Large: The server is unwilling to process the request because header fields are too large.
451 Unavailable For Legal Reasons: The server operator has received a legal demand to deny access.

-- 5xx Server Error Statuses --
500 Internal Server Error: A generic error message given when an unexpected condition was encountered.
501 Not Implemented: The server either does not recognize the request method or lacks the ability to fulfill it.
502 Bad Gateway: The server, while acting as a gateway or proxy, received an invalid response from the upstream server.
503 Service Unavailable: The server cannot handle the request (due to temporary overloading or maintenance).
504 Gateway Timeout: The server, while acting as a gateway or proxy, did not receive a timely response.
505 HTTP Version Not Supported: The server does not support the HTTP protocol version used in the request.
506 Variant Also Negotiates: Transparent content negotiation for the request results in a circular reference.
507 Insufficient Storage: The server is unable to store the representation needed to complete the request.
508 Loop Detected: The server detected an infinite loop while processing the request.
510 Not Extended: Further extensions to the request are required for the server to fulfill it.
511 Network Authentication Required: The client needs to authenticate to gain network access.
'''
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel #defines and validates the expected request body.
import ask_nlp
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_app):
    # Open Gold once, while the server is starting, so the first question does not pay for login.
    try:
        ask_nlp.query_gold("SELECT 1 AS ok")
    except Exception:
        pass
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, #Cross-Origin Resource Sharing Postman
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["POST", "OPTIONS"], #The HTTP OPTIONS method asks a server what actions, methods, or features are allowed for a specific URL or the entire server.
    allow_headers=["*"], #common headers --> Authorization: Bearer <token>, Content-Type: application/json, Accept: application/json.
)

class PriorTurn(BaseModel):
    question: str = ""
    sql: str = ""
    columns: list[str] = []

class AskBody(BaseModel): #Pydantic model that defines the expected request body for the /ask endpoint. basically, data validation.
    question: str
    history: list[PriorTurn] = []

@app.post("/ask") #When somebody sends a POST request to /ask, execute the ask() function.
def ask(body: AskBody):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question.")

    history = [turn.model_dump() for turn in body.history[-4:]]
    try:
        return ask_nlp.run(question, history)
    except SystemExit as exc:
        detail = exc.code if isinstance(exc.code, str) else "The query failed."
        raise HTTPException(status_code=500, detail=detail)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))