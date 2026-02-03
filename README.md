# RoomSync - Household Management App

Team 6 RoomSync is a web application designed to simplify household management. It features secure user authentication, group management, shared grocery lists, and receipt scanning powered by Google Document AI.

**[🚀 Live Demo](https://team6-roomsync.vercel.app)**

## Features
-   **Group Management**: Create or join household groups with unique codes.
-   **Authentication**: Secure login and registration.
-   **Groceries**: Shared list with real-time updates.
-   **Receipt Scanning**: Upload receipts to automatically parse items and prices using AI.

## Deployment (Vercel)

This project is deployed on [Vercel](https://vercel.com).

**Live URL**: `https://team6-roomsync.vercel.app`

### Environment Variables
For the application to function correctly, the following environment variables must be set in Vercel:
-   `SECRET_KEY`: Random string for session security.
-   `DATABASE_URL`: `sqlite:///household.db` (Note: Vercel uses `/tmp/household.db` automatically).
-   `GOOGLE_CLOUD_PROJECT`: Your GCP Project ID.
-   `DOCUMENT_AI_LOCATION`: e.g., `us`.
-   `DOCUMENT_AI_PROCESSOR_ID`: Your Processor ID.
-   `GOOGLE_CREDENTIALS_JSON`: The **content** of your Service Account JSON key.

### ⚠️ Database Persistence Note
This application currently uses **SQLite**. On Vercel's serverless environment, the filesystem (and thus the database) is **ephemeral**.
-   **Data will reset** frequently (on redeploy or cold start).
-   **Recommendation**: For a production application, migrate to a hosted database like Vercel Postgres, Supabase, or Neon.

## Local Development

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/zkisaboss/Team6_RoomSync.git
    cd Team6_RoomSync
    ```

2.  **Set up Virtual Environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure `.env`**:
    Create a `.env` file in the root directory:
    ```bash
    SECRET_KEY=dev-key
    DATABASE_URL=sqlite:///household.db
    # Add Google Cloud credentials here
    ```

4.  **Run the App**:
    ```bash
    python3 app.py
    ```
    Visit `http://127.0.0.1:5000`.