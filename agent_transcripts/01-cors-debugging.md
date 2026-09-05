# Agent Transcript 01 — CORS Debugging

## Problem

The frontend was unable to communicate with the FastAPI backend because the browser blocked the request due to CORS.

The frontend was running on a Vite development server such as:

- `http://localhost:5173`
- Later, because the port was already in use, Vite ran on `http://localhost:5174`

The backend was running on:

`http://127.0.0.1:8000`

## Initial Symptom

The browser console reported:

> Access to fetch at 'http://127.0.0.1:8000/ask' from origin 'http://localhost:5174' has been blocked by CORS policy.

The preflight request was also returning:

```text
OPTIONS /ask HTTP/1.1" 400 Bad Request