import requests
import time
from datetime import datetime
import pandas as pd
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
API_KEY = api_key
SPORT = 'upcoming'
REGIONS = 'us'
MARKETS = 'h2h'
ODDS_FORMAT = 'decimal'
DATE_FORMAT = 'unix'
BET_SIZE = 100

# Email/SMS Configuration
EMAIL_ADDRESS = email
EMAIL_PASSWORD = password
PHONE_NUMBER = number
CARRIER = "AT&T"  # AT&T, Verizon, T-Mobile, Sprint

# Bookmakers to exclude
EXCLUDED_BOOKMAKERS = [
    'pointsbetus', 'fanduel', 'barstool', 'betmgm', 'gtbets', 'foxbet',
    'sugarhouse', 'betfair', 'unibet_us', 'williamhill_us', 'twinspires',
    'circasports', 'onexbet', 'wynnbet', 'superbook', 'betrivers', 'lowvig',
    'betonlineag', 'mybookieag', 'betus'
]

# Carrier email-to-SMS gateways
CARRIER_GATEWAYS = {
    'AT&T': '@txt.att.net',
    'Verizon': '@vtext.com',
    'T-Mobile': '@tmomail.net',
    'Sprint': '@messaging.sprintpcs.com'
}


def send_email(to_email, subject, body):
    """Send email using SMTP (deprecated but works)"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ADDRESS, to_email, text)
        server.quit()
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_sms_via_email(phone_number, message, carrier, email_credentials=None, subject="Arbitrage Alert"):
    """Send SMS via email-to-SMS gateway (vtext for Verizon, etc.)"""
    try:
        gateway = CARRIER_GATEWAYS.get(carrier, '@vtext.com')  # Default to Verizon
        sms_email = f"{phone_number}{gateway}"
        
        msg = MIMEText(message)
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = sms_email
        msg['Subject'] = subject
        
        if email_credentials:
            email_addr, email_pass = email_credentials
        else:
            email_addr, email_pass = EMAIL_ADDRESS, EMAIL_PASSWORD
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_addr, email_pass)
        server.sendmail(email_addr, sms_email, msg.as_string())
        server.quit()
        print(f"SMS sent to {phone_number} via {carrier}")
        return True
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False


def remove_bookmaker(games, bookmaker_key):
    """Remove a bookmaker from all games"""
    for item in games:
        if 'bookmakers' in item:
            item['bookmakers'] = [bookmaker for bookmaker in item['bookmakers'] 
                                 if bookmaker['key'] != bookmaker_key]


class Event:
    def __init__(self, data):
        self.data = data
        self.sport_key = data.get('sport_key', 'unknown')
        self.id = data.get('id', 'unknown')
        self.commence_time = data.get('commence_time', 0)
        self.best_odds = None
        self.num_outcomes = 0
        self.total_arbitrage_percentage = 0
        self.expected_earnings = 0
        self.bet_amounts = []

    def find_best_odds(self):
        """Find the best odds for each outcome across all bookmakers"""
        if not self.data.get('bookmakers'):
            return None
        
        # Get number of outcomes from first bookmaker
        try:
            num_outcomes = len(self.data['bookmakers'][0]['markets'][0]['outcomes'])
        except (IndexError, KeyError):
            return None
        
        self.num_outcomes = num_outcomes
        
        best_odds = [[None, None, float('-inf')] for _ in range(num_outcomes)]
        
        for bookmaker in self.data['bookmakers']:
            try:
                markets = bookmaker.get('markets', [])
                if not markets:
                    continue
                
                outcomes = markets[0].get('outcomes', [])
                if len(outcomes) != num_outcomes:
                    continue
                
                for outcome_idx in range(num_outcomes):
                    try:
                        bookmaker_odds = float(outcomes[outcome_idx]['price'])
                        current_best = best_odds[outcome_idx][2]
                        
                        if bookmaker_odds > current_best:
                            best_odds[outcome_idx][0] = bookmaker.get('title', 'Unknown')
                            best_odds[outcome_idx][1] = outcomes[outcome_idx].get('name', 'Unknown')
                            best_odds[outcome_idx][2] = bookmaker_odds
                    except (KeyError, ValueError, IndexError):
                        continue
            except (KeyError, IndexError):
                continue
        
        # Check if we found valid odds for all outcomes
        if any(odds[2] == float('-inf') for odds in best_odds):
            return None
        
        self.best_odds = best_odds
        return best_odds

    def arbitrage(self):
        """Check if arbitrage opportunity exists"""
        if not self.best_odds:
            return False
        
        total_arbitrage_percentage = 0.0
        for odds in self.best_odds:
            if odds[2] <= 0:  
                return False
            total_arbitrage_percentage += (1.0 / odds[2])
        
        self.total_arbitrage_percentage = total_arbitrage_percentage
        self.expected_earnings = (BET_SIZE / total_arbitrage_percentage) - BET_SIZE
        
        # Arbitrage exists if sum of reciprocals < 1
        return total_arbitrage_percentage < 1.0

    def convert_decimal_to_american(self):
        """Convert decimal odds to American odds"""
        if not self.best_odds:
            return None
        
        for odds in self.best_odds:
            decimal = odds[2]
            if decimal >= 2:
                american = (decimal - 1) * 100
            else:
                american = -100 / (decimal - 1)
            odds[2] = round(american, 2)
        
        return self.best_odds

    def calculate_arbitrage_bets(self):
        """Calculate optimal bet amounts for arbitrage"""
        if not self.best_odds or self.total_arbitrage_percentage == 0:
            return None
        
        bet_amounts = []
        for outcome_idx in range(self.num_outcomes):
            individual_arbitrage_percentage = 1.0 / self.best_odds[outcome_idx][2]
            bet_amount = (BET_SIZE * individual_arbitrage_percentage) / self.total_arbitrage_percentage
            bet_amounts.append(round(bet_amount, 2))
        
        self.bet_amounts = bet_amounts
        return bet_amounts


def fetch_odds():
    """Fetch odds from the API"""
    try:
        response = requests.get(
            f'https://api.the-odds-api.com/v4/sports/{SPORT}/odds',
            params={
                'api_key': API_KEY,
                'regions': REGIONS,
                'markets': MARKETS,
                'oddsFormat': ODDS_FORMAT,
                'dateFormat': DATE_FORMAT,
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching odds: {e}")
        return []


def process_events(odds_response):
    """Process odds data and find arbitrage opportunities"""
    now = time.time()
    
    valid_games = [
        game for game in odds_response 
        if game.get('bookmakers') and game.get('commence_time', 0) > now
    ]
    
    # Remove excluded bookmakers
    for bookmaker_key in EXCLUDED_BOOKMAKERS:
        remove_bookmaker(valid_games, bookmaker_key)
    
    valid_games = [game for game in valid_games if game.get('bookmakers')]
    
    events = [Event(data) for data in valid_games]
    
    arbitrage_events = []
    for event in events:
        best_odds = event.find_best_odds()
        if best_odds and event.arbitrage():
            arbitrage_events.append(event)
    
    return arbitrage_events


def send_arbitrage_alerts(arbitrage_events):
    """Send alerts for arbitrage opportunities"""
    for event in arbitrage_events:
        event.calculate_arbitrage_bets()
        event.convert_decimal_to_american()
        
        # Build message
        message_parts = []
        message_parts.append(f"ARBITRAGE FOUND!\n")
        message_parts.append(f"Event ID: {event.id}")
        message_parts.append(f"Sport: {event.sport_key}")
        message_parts.append(f"Expected Earnings: ${event.expected_earnings:.2f}\n")
        
        for idx, outcome in enumerate(event.best_odds):
            bookmaker = outcome[0]
            name = outcome[1]
            odds = outcome[2]
            amount = event.bet_amounts[idx]
            message_parts.append(f"{name} at {odds} on {bookmaker} (Bet ${amount:.2f})")
        
        message = "\n".join(message_parts)
        
        # Send SMS
        send_sms_via_email(
            PHONE_NUMBER, 
            message, 
            CARRIER,
            (EMAIL_ADDRESS, EMAIL_PASSWORD),
            subject="ARB FOUND!"
        )
        
        # Send Email
        send_email(
            EMAIL_ADDRESS,
            "ARBITRAGE OPPORTUNITY FOUND!",
            message
        )
        
        print(f"\n{message}\n")


def create_dataframe(arbitrage_events):
    """Create pandas DataFrame for arbitrage events"""
    if not arbitrage_events:
        return pd.DataFrame()
    
    max_outcomes = max([event.num_outcomes for event in arbitrage_events])
    
    columns = ['ID', 'Sport Key', 'Expected Earnings']
    for outcome in range(1, max_outcomes + 1):
        columns.extend([
            f'Bookmaker #{outcome}',
            f'Name #{outcome}',
            f'Odds #{outcome}',
            f'Amount to Bet #{outcome}'
        ])
    
    dataframe = pd.DataFrame(columns=columns)
    
    for event in arbitrage_events:
        row = [event.id, event.sport_key, round(event.expected_earnings, 2)]
        
        for idx in range(event.num_outcomes):
            row.extend([
                event.best_odds[idx][0],
                event.best_odds[idx][1],
                event.best_odds[idx][2],
                event.bet_amounts[idx]
            ])
        
        # Pad row if needed
        while len(row) < len(columns):
            row.append('N/A')
        
        dataframe.loc[len(dataframe.index)] = row
    
    return dataframe


def main():
    """Main function to run arbitrage detection"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching odds...")
    
    odds_response = fetch_odds()
    if not odds_response:
        print("No odds data received")
        return
    
    print(f"Processing {len(odds_response)} events...")
    
    arbitrage_events = process_events(odds_response)
    
    if arbitrage_events:
        print(f"\n*** FOUND {len(arbitrage_events)} ARBITRAGE OPPORTUNITY(IES) ***")
        send_arbitrage_alerts(arbitrage_events)
        
        df = create_dataframe(arbitrage_events)
        if not df.empty:
            print("\nArbitrage Summary:")
            print(df.to_string(index=False))
    else:
        print("No arbitrage opportunities found")


if __name__ == "__main__":
    print("Arbitrage Detection Tool Started")
    print("Checking for opportunities every 60 seconds...")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            main()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        raise
