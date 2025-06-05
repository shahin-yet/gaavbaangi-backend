# Backend Service

This is the backend service for the Telegram WebApp project, built with Flask.

## Project Structure

```
backend/
├── app.py              # Flask backend application
├── requirements.txt    # Python dependencies
├── Procfile           # Railway deployment configuration
└── .env.example       # Example environment variables
```

## Deployment on Railway

1. Create a new project on Railway
2. Connect your GitHub repository
3. Configure the following settings:
   - Name: `your-project-backend`
   - Environment: `Python`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Plan: Free or paid based on your needs
4. Add environment variables from `.env.example` in Railway's dashboard
5. Deploy the service

## Local Development

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your values
5. Run the development server:
   ```bash
   flask run
   ```

## GitHub Integration

1. Create a new repository on GitHub
2. Push your code to the repository
3. Set up GitHub Actions for automated testing (optional)
4. Configure GitHub Secrets for sensitive data:
   - `RAILWAY_TOKEN`: Your Railway API token
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token

## Security Notes

- Never commit your `.env` file
- Always validate Telegram WebApp init data
- Use HTTPS for all communications
- Implement proper error handling and rate limiting
- Keep your Railway service URLs private and only share them with necessary team members
- Use GitHub Secrets for storing sensitive information 