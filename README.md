# DeloConnect Backend

A FastAPI-based backend application for DeloConnect, featuring employee management, chat functionality, and HR operations.

## Features

- Employee Management System
- Real-time Chat System
- HR Operations Dashboard
- Authentication & Authorization
- MongoDB Database Integration
- WebSocket Support for Real-time Updates
- API Documentation with Swagger UI

## Prerequisites

- Python 3.8 or higher
- MongoDB Atlas account (or other hosted MongoDB service)
- Docker (optional, for containerized deployment)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd backend
```

2. Create and activate a virtual environment:
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Environment Setup

1. Create a `.env.dev` file in the root directory:
```bash
cp .env.sample .env.dev
```

2. Configure the environment variables in `.env.dev`:
```env
# Database Configuration
DATABASE_URL=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/<database>?retryWrites=true&w=majority

# Security Configuration
secret_key=your-secure-secret-key-here

# Email Configuration
sender_email=your-email@example.com
sender_password=your-email-password
email_template=path/to/email/template.html
admin_email_template=path/to/admin/email/template.html

# LLM Configuration
LLM_ADDR=http://your-llm-service:port
```

Note: Replace the DATABASE_URL with your actual MongoDB Atlas connection string. You can get this from your MongoDB Atlas dashboard:
1. Go to your cluster
2. Click "Connect"
3. Choose "Connect your application"
4. Copy the connection string and replace `<username>`, `<password>`, `<cluster>`, and `<database>` with your actual values

## Running the Application

### Option 1: Using Docker Compose (Recommended)

1. Build and run the application:
```bash
docker-compose up --build
```

2. Access the application at `http://localhost:8080`

### Option 2: Local Development

1. Run the application:
```bash
python main.py
```

The application will be available at `http://localhost:8080`

## API Documentation

Once the application is running, you can access the API documentation at:

- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`

## Project Structure

```
backend/
├── main.py               # Application running point
├── app.py                # Application entry point
├── auth/                 # Authentication
├── employee_filtering/   # Employee filtering API
├── config/               # Configuration files
├── models/               # Database models
├── routes/               # API routes
├── utils/                # Utility functions
```

## Development

1. Make sure you have a valid MongoDB Atlas connection string in your `.env.dev` file
2. Update other environment variables as needed
3. Run the application using either Docker Compose or directly with Python
4. Access the API documentation to test endpoints

## Notes

- The application uses MongoDB Atlas for data storage
- Email functionality requires proper SMTP configuration
- LLM integration requires a running LLM service
- WebSocket endpoints are available for real-time updates
