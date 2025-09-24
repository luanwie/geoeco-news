from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from typing import Optional
from contextlib import asynccontextmanager
import asyncio
import threading
from apscheduler.schedulers.background import BackgroundScheduler

from models import get_db, create_tables, User, UserCategory, Alert, NewsItem
from scraper import run_news_scraper
from whatsapp import send_whatsapp_alert, validate_brazilian_phone

# Background scheduler for news scraping
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables on startup
    create_tables()
    
    # Start the background scheduler for news scraping
    scheduler.add_job(
        func=process_alerts_pipeline,
        trigger="interval",
        minutes=15,
        id="news_scraper",
        name="News Scraper and Alert Processor"
    )
    scheduler.start()
    print("Background scheduler started for news scraping every 15 minutes")
    
    # Run initial scrape
    threading.Thread(target=process_alerts_pipeline, daemon=True).start()
    
    yield
    
    # Cleanup on shutdown
    scheduler.shutdown()

app = FastAPI(title="News Alert SaaS", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("SESSION_SECRET")
if not SECRET_KEY:
    raise ValueError("SESSION_SECRET environment variable is required")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.email == email).first()
    return user

def require_auth(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user

def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Optional dependency to get current user if authenticated"""
    try:
        return get_current_user(request, db)
    except:
        return None

def process_alerts_pipeline():
    """Background task to scrape news and send alerts to users"""
    try:
        # Run news scraper
        run_news_scraper()
        
        # Process unprocessed news items and send alerts
        db = next(get_db())
        
        # Get unprocessed high-impact news
        unprocessed_news = db.query(NewsItem).filter(
            NewsItem.processed == False,
            NewsItem.impact_score >= 2  # High impact requirement
        ).all()
        
        for news_item in unprocessed_news:
            # Get users interested in this category with active plans
            users_query = db.query(User, UserCategory).join(
                UserCategory, User.id == UserCategory.user_id
            ).filter(
                # Check if user wants this category
                ((news_item.category == "economy") & (UserCategory.economy == True)) |
                ((news_item.category == "geopolitics") & (UserCategory.geopolitics == True)) |
                ((news_item.category == "markets") & (UserCategory.markets == True))
            ).filter(
                # Check if user has active plan or trial
                (User.plan != "free") | (User.trial_expires > datetime.utcnow())
            )
            
            for user, category in users_query.all():
                try:
                    # Check if alert already sent to this user for this news
                    existing_alert = db.query(Alert).filter(
                        Alert.user_id == user.id,
                        Alert.news_url == news_item.url
                    ).first()
                    
                    if existing_alert:
                        continue
                    
                    # Create alert record
                    alert = Alert(
                        user_id=user.id,
                        title=news_item.title,
                        content=news_item.content,
                        category=news_item.category,
                        news_url=news_item.url
                    )
                    db.add(alert)
                    
                    # Send WhatsApp alert
                    success = send_whatsapp_alert(
                        to_phone_number=str(user.phone),
                        title=str(news_item.title),
                        category=str(news_item.category),
                        summary=str(news_item.content),
                        news_url=str(news_item.url),
                        published_time=news_item.published_at
                    )
                    
                    if success:
                        print(f"Alert sent to user {user.email} for news: {news_item.title[:50]}...")
                    else:
                        print(f"Failed to send alert to user {user.email}")
                        
                except Exception as e:
                    print(f"Error sending alert to user {user.email}: {e}")
                    continue
            
            # Mark news as processed
            db.query(NewsItem).filter(NewsItem.id == news_item.id).update({"processed": True})
        
        db.commit()
        db.close()
        print(f"Processed {len(unprocessed_news)} news items")
        
    except Exception as e:
        print(f"Error in alert processing pipeline: {e}")

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page with hero section and pricing"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """User registration page"""
    next_url = request.query_params.get('next', '/dashboard')
    plan = request.query_params.get('plan', '')
    return templates.TemplateResponse("signup.html", {
        "request": request,
        "next_url": next_url,
        "plan": plan
    })

@app.post("/signup")
async def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    plan: str = Form(""),
    db: Session = Depends(get_db)
):
    """Process user registration"""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "signup.html", 
            {"request": request, "error": "Email already registered", "next_url": next, "plan": plan}
        )
    
    # Validate phone number format
    try:
        validated_phone = validate_brazilian_phone(phone)
    except ValueError as e:
        return templates.TemplateResponse(
            "signup.html", 
            {"request": request, "error": str(e), "next_url": next, "plan": plan}
        )
    
    # Create new user
    hashed_password = get_password_hash(password)
    user = User(
        name=name,
        email=email,
        phone=validated_phone,
        hashed_password=hashed_password,
        plan="free"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create default categories for user
    categories = UserCategory(
        user_id=user.id,
        economy=True,
        geopolitics=True,
        markets=True
    )
    db.add(categories)
    db.commit()
    
    # Create access token and redirect appropriately
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # Handle redirect with plan parameter (sanitized)
    allowed_redirects = ['/dashboard', '/pricing', '/settings']
    safe_next = next if next in allowed_redirects else '/dashboard'
    
    if plan and safe_next == '/pricing':
        redirect_url = f"/pricing?plan={plan}"
    else:
        redirect_url = safe_next
    
    # Check if running in development (non-HTTPS)
    is_dev = os.getenv('REPLIT_DEV_DOMAIN') is not None or 'localhost' in request.headers.get('host', '')
    
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key="access_token", 
        value=access_token, 
        httponly=True,
        secure=not is_dev,  # Only secure in production
        samesite="lax"
    )
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """User login page"""
    next_url = request.query_params.get('next', '/dashboard')
    plan = request.query_params.get('plan', '')
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next_url": next_url,
        "plan": plan
    })

@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    plan: str = Form(""),
    db: Session = Depends(get_db)
):
    """Process user login"""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Invalid email or password", "next_url": next, "plan": plan}
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # Handle redirect with plan parameter (sanitized)
    allowed_redirects = ['/dashboard', '/pricing', '/settings']
    safe_next = next if next in allowed_redirects else '/dashboard'
    
    if plan and safe_next == '/pricing':
        redirect_url = f"/pricing?plan={plan}"
    else:
        redirect_url = safe_next
    
    # Check if running in development (non-HTTPS)
    is_dev = os.getenv('REPLIT_DEV_DOMAIN') is not None or 'localhost' in request.headers.get('host', '')
    
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key="access_token", 
        value=access_token, 
        httponly=True,
        secure=not is_dev,  # Only secure in production
        samesite="lax"
    )
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """User dashboard with alert history and account status"""
    
    # Get user categories
    categories = db.query(UserCategory).filter(UserCategory.user_id == user.id).first()
    
    # Get last 10 alerts
    recent_alerts = db.query(Alert).filter(Alert.user_id == user.id)\
        .order_by(Alert.sent_at.desc()).limit(10).all()
    
    # Check if trial expired and calculate days remaining
    trial_active = False
    days_remaining = 0
    if user.plan == "free" and user.trial_expires:
        trial_active = user.trial_expires > datetime.utcnow()
        if trial_active:
            days_remaining = (user.trial_expires - datetime.utcnow()).days
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "categories": categories,
        "recent_alerts": recent_alerts,
        "trial_active": trial_active,
        "days_remaining": days_remaining
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """User settings page"""
    
    categories = db.query(UserCategory).filter(UserCategory.user_id == user.id).first()
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "categories": categories
    })

@app.post("/settings")
async def update_settings(
    request: Request,
    phone: str = Form(...),
    economy: bool = Form(False),
    geopolitics: bool = Form(False),
    markets: bool = Form(False),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update user settings"""
    
    # Validate phone number format
    try:
        validated_phone = validate_brazilian_phone(phone)
    except ValueError as e:
        categories = db.query(UserCategory).filter(UserCategory.user_id == user.id).first()
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "user": user, "categories": categories, "error": str(e)}
        )
    
    # Update phone number
    db.query(User).filter(User.id == user.id).update({"phone": validated_phone})
    
    # Update categories
    categories = db.query(UserCategory).filter(UserCategory.user_id == user.id).first()
    if categories:
        db.query(UserCategory).filter(UserCategory.user_id == user.id).update({
            "economy": economy,
            "geopolitics": geopolitics, 
            "markets": markets
        })
    else:
        categories = UserCategory(
            user_id=user.id,
            economy=economy,
            geopolitics=geopolitics,
            markets=markets
        )
        db.add(categories)
    
    db.commit()
    
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/logout")
async def logout():
    """User logout"""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        key="access_token",
        secure=True,
        samesite="lax"
    )
    return response

@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """Pricing page with conversion tactics"""
    return templates.TemplateResponse("pricing.html", {
        "request": request,
        "user": user
    })

# Stripe integration routes
@app.post("/create-checkout-session")
async def create_checkout_session(
    request: Request,
    plan_type: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create Stripe checkout session for Pro subscription"""
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    
    if not stripe.api_key:
        return RedirectResponse(url="/dashboard?error=stripe_not_configured", status_code=303)
    
    # Define prices from environment variables
    prices = {
        "pro_monthly": os.getenv("STRIPE_PRICE_MONTHLY", "price_1234_monthly"),
        "pro_annual": os.getenv("STRIPE_PRICE_ANNUAL", "price_1234_annual")
    }
    
    try:
        # Get domain for redirect URLs
        domain = os.getenv('REPLIT_DEV_DOMAIN')
        if not domain:
            domains = os.getenv('REPLIT_DOMAINS')
            domain = domains.split(',')[0] if domains else 'localhost:5000'
        
        # Create Stripe customer if not exists
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=str(user.email),
                name=str(user.name),
                phone=str(user.phone)
            )
            db.query(User).filter(User.id == user.id).update({"stripe_customer_id": customer.id})
            db.commit()
            user.stripe_customer_id = customer.id
        
        checkout_session = stripe.checkout.Session.create(
            customer=str(user.stripe_customer_id),
            line_items=[{
                'price': prices.get(plan_type, prices["pro_monthly"]),
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f'https://{domain}/dashboard?payment=success',
            cancel_url=f'https://{domain}/dashboard?payment=cancelled',
            metadata={
                'user_id': str(user.id),
                'plan_type': plan_type
            }
        )
        return RedirectResponse(url=checkout_session.url, status_code=303)
    except Exception as e:
        print(f"Stripe checkout error: {e}")
        return RedirectResponse(url="/dashboard?error=payment_failed", status_code=303)

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events"""
    import stripe
    
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        # Invalid payload
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata'].get('user_id')
        plan_type = session['metadata'].get('plan_type')
        
        if user_id:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                # Update user plan
                plan_value = 'pro_annual' if plan_type == 'pro_annual' else 'pro'
                db.query(User).filter(User.id == user.id).update({
                    "plan": plan_value,
                    "stripe_customer_id": session['customer']
                })
                db.commit()
                print(f"Updated user {user.email} to plan {user.plan}")
    
    elif event['type'] == 'customer.subscription.deleted':
        # Handle subscription cancellation
        subscription = event['data']['object']
        customer_id = subscription['customer']
        
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            db.query(User).filter(User.id == user.id).update({"plan": "free"})
            db.commit()
            print(f"Downgraded user {user.email} to free plan")
    
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000, reload=False)