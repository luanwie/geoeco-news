import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import NewsItem, SessionLocal
import time
from typing import List, Dict
import re

# Keywords for filtering economic and geopolitical news
ECONOMIC_KEYWORDS = [
    "economia", "mercado", "inflação", "pib", "juros", "selic", "dólar", "real", 
    "bolsa", "bovespa", "nasdaq", "investimento", "banco central", "fed", "economia",
    "recessão", "crescimento", "desemprego", "exportação", "importação"
]

GEOPOLITICAL_KEYWORDS = [
    "geopolítica", "eleição", "guerra", "conflito", "diplomacia", "otan", "onu",
    "china", "estados unidos", "rússia", "política internacional", "sanções",
    "acordo", "tratado", "presidente", "governo", "parlamento", "congresso"
]

MARKET_KEYWORDS = [
    "ações", "commodities", "petróleo", "ouro", "crypto", "bitcoin", "ethereum",
    "forex", "câmbio", "trading", "hedge fund", "ipo", "fusão", "aquisição"
]

class NewsScraper:
    def __init__(self):
        self.sources = [
            {
                "name": "Reuters Brasil",
                "url": "https://www.reuters.com/world/americas/brazil/",
                "selector": "article"
            },
            {
                "name": "G1 Economia", 
                "url": "https://g1.globo.com/economia/",
                "selector": "article"
            },
            {
                "name": "InfoMoney",
                "url": "https://www.infomoney.com.br/mercados/",
                "selector": "article"
            }
        ]
        
    def extract_text_from_url(self, url: str) -> str:
        """Extract article text from URL"""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try common content selectors
            content_selectors = [
                'article p',
                '.content p', 
                '.article-content p',
                '.post-content p',
                'main p'
            ]
            
            content = ""
            for selector in content_selectors:
                paragraphs = soup.select(selector)
                if paragraphs:
                    content = " ".join([p.get_text().strip() for p in paragraphs[:5]])
                    break
            
            return content[:500] if content else "Conteúdo não disponível"
            
        except Exception as e:
            print(f"Error extracting content from {url}: {e}")
            return "Erro ao extrair conteúdo"
    
    def categorize_news(self, title: str, content: str) -> str:
        """Categorize news based on keywords"""
        text = (title + " " + content).lower()
        
        economic_score = sum(1 for keyword in ECONOMIC_KEYWORDS if keyword in text)
        geopolitical_score = sum(1 for keyword in GEOPOLITICAL_KEYWORDS if keyword in text)
        market_score = sum(1 for keyword in MARKET_KEYWORDS if keyword in text)
        
        scores = {
            "economy": economic_score,
            "geopolitics": geopolitical_score,
            "markets": market_score
        }
        
        return max(scores, key=scores.get) if max(scores.values()) > 0 else "economy"
    
    def scrape_source(self, source: Dict) -> List[Dict]:
        """Scrape news from a single source"""
        articles = []
        
        try:
            response = requests.get(source["url"], timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find articles
            article_elements = soup.select(source["selector"])[:10]  # Limit to 10 articles
            
            for article in article_elements:
                try:
                    # Extract title
                    title_elem = article.find(['h1', 'h2', 'h3', 'h4'])
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text().strip()
                    if len(title) < 10:  # Skip very short titles
                        continue
                    
                    # Extract URL
                    link_elem = article.find('a', href=True)
                    if not link_elem:
                        continue
                    
                    url = link_elem['href']
                    if url.startswith('/'):
                        base_url = '/'.join(source["url"].split('/')[:3])
                        url = base_url + url
                    
                    # Extract content
                    content = self.extract_text_from_url(url)
                    
                    # Categorize
                    category = self.categorize_news(title, content)
                    
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": url,
                        "source": source["name"],
                        "category": category,
                        "published_at": datetime.utcnow()  # Simplified - in real app, extract actual date
                    })
                    
                except Exception as e:
                    print(f"Error processing article: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error scraping {source['name']}: {e}")
        
        return articles
    
    def calculate_impact_score(self, title: str) -> int:
        """Calculate impact score based on title analysis"""
        high_impact_terms = [
            "quebra", "crash", "crise", "emergência", "urgente", 
            "histórico", "recorde", "máxima", "mínima", "alerta"
        ]
        
        title_lower = title.lower()
        score = 1
        
        for term in high_impact_terms:
            if term in title_lower:
                score += 1
        
        return min(score, 5)  # Cap at 5
    
    def scrape_all_sources(self):
        """Scrape all configured news sources"""
        db = SessionLocal()
        all_articles = []
        
        try:
            for source in self.sources:
                print(f"Scraping {source['name']}...")
                articles = self.scrape_source(source)
                all_articles.extend(articles)
            
            # Process and save articles
            for article_data in all_articles:
                # Check if article already exists
                existing = db.query(NewsItem).filter(NewsItem.url == article_data["url"]).first()
                if existing:
                    continue
                
                # Calculate impact score
                impact_score = self.calculate_impact_score(article_data["title"])
                
                # Create news item
                news_item = NewsItem(
                    title=article_data["title"],
                    content=article_data["content"],
                    url=article_data["url"],
                    source=article_data["source"],
                    category=article_data["category"],
                    published_at=article_data["published_at"],
                    impact_score=impact_score,
                    processed=False
                )
                
                db.add(news_item)
            
            db.commit()
            print(f"Saved {len(all_articles)} new articles")
            
        except Exception as e:
            print(f"Error in scraping process: {e}")
            db.rollback()
        finally:
            db.close()

def run_news_scraper():
    """Function to run the news scraper"""
    scraper = NewsScraper()
    scraper.scrape_all_sources()

if __name__ == "__main__":
    # For standalone testing
    run_news_scraper()