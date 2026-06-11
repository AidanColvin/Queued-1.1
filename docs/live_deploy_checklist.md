# Live deploy checklist

## Frontend
- Production frontend URL should look like:
  - https://queued-2.vercel.app
- Do not append terminal text, usernames, or shell prompts to the URL.

## Backend
- Deploy FastAPI to Render or another public host.
- Example backend URL:
  - https://your-backend-name.onrender.com

## Required frontend env var
- NEXT_PUBLIC_API_BASE_URL=https://your-backend-name.onrender.com

## Test URLs
- Frontend:
  - https://queued-2.vercel.app
- Backend health:
  - https://your-backend-name.onrender.com/health
- Backend recommendations:
  - https://your-backend-name.onrender.com/api/recommendations/1?top_n=10
