"""
Vercel entry point — wraps the FastAPI app with Mangum for serverless deployment.
Vercel's Python runtime calls `handler` for every incoming request.
"""
from mangum import Mangum
from main import app

handler = Mangum(app, lifespan="auto")
