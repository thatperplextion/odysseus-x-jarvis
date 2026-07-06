"""
Sentiment Analysis System for Jarvis OS - Phase 2 Component
Analyze emotional tone and sentiment in text
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
import re
from collections import defaultdict

logger = logging.getLogger(__name__)


class Sentiment(Enum):
    """Types of sentiment"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class SentimentIntensity(Enum):
    """Intensity levels for sentiment"""
    VERY_POSITIVE = 0.8
    POSITIVE = 0.6
    SLIGHTLY_POSITIVE = 0.1
    NEUTRAL = 0.0
    SLIGHTLY_NEGATIVE = -0.1
    NEGATIVE = -0.6
    VERY_NEGATIVE = -0.8


@dataclass
class SentimentResult:
    """Result of sentiment analysis"""
    sentiment: Sentiment
    intensity: float
    confidence: float
    positive_score: float
    negative_score: float
    neutral_score: float
    emotions: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment": self.sentiment.value,
            "intensity": self.intensity,
            "confidence": self.confidence,
            "positive_score": self.positive_score,
            "negative_score": self.negative_score,
            "neutral_score": self.neutral_score,
            "emotions": self.emotions,
            "metadata": self.metadata
        }


class SentimentAnalyzer:
    """Sentiment analysis system for emotional tone detection"""
    
    def __init__(self):
        self.positive_words: Set[str] = set()
        self.negative_words: Set[str] = set()
        self.emotion_lexicon: Dict[str, str] = {}
        self.analysis_counter = 0
        self.analysis_history: List[Dict[str, Any]] = []
        
        # Initialize lexicons
        self._initialize_lexicons()
        
        logger.info("Sentiment analysis system initialized")
    
    def _initialize_lexicons(self):
        """Initialize sentiment and emotion lexicons"""
        
        # Positive words
        self.positive_words.update([
            "good", "great", "excellent", "amazing", "wonderful", "fantastic",
            "awesome", "brilliant", "perfect", "love", "happy", "joy",
            "pleased", "satisfied", "delighted", "thrilled", "excited",
            "success", "successful", "win", "winner", "best", "better",
            "improve", "improvement", "helpful", "useful", "effective",
            "efficient", "fast", "quick", "easy", "simple", "clear",
            "thanks", "thank you", "appreciate", "grateful", "glad"
        ])
        
        # Negative words
        self.negative_words.update([
            "bad", "terrible", "awful", "horrible", "poor", "worst",
            "hate", "dislike", "angry", "frustrated", "annoyed", "upset",
            "disappointed", "sad", "unhappy", "depressed", "worried",
            "concerned", "anxious", "stressed", "overwhelmed", "confused",
            "fail", "failure", "error", "mistake", "wrong", "problem",
            "issue", "bug", "broken", "slow", "difficult", "hard",
            "complex", "complicated", "unclear", "confusing", "sorry",
            "apologize", "regret", "unfortunately", "cannot", "unable"
        ])
        
        # Emotion lexicon
        self.emotion_lexicon.update({
            "joy": ["happy", "excited", "thrilled", "delighted", "pleased"],
            "sadness": ["sad", "unhappy", "depressed", "disappointed", "down"],
            "anger": ["angry", "furious", "mad", "irritated", "annoyed"],
            "fear": ["scared", "afraid", "worried", "anxious", "concerned"],
            "surprise": ["surprised", "shocked", "amazed", "astonished"],
            "disgust": ["disgusted", "revolted", "repulsed"],
            "trust": ["trust", "confident", "secure", "safe"],
            "anticipation": ["excited", "eager", "looking forward", "expect"]
        })
    
    def add_sentiment_words(self, positive: List[str] = None, negative: List[str] = None):
        """Add custom sentiment words"""
        if positive:
            self.positive_words.update(positive)
            logger.info(f"Added {len(positive)} positive words")
        
        if negative:
            self.negative_words.update(negative)
            logger.info(f"Added {len(negative)} negative words")
    
    def analyze_sentiment(self, text: str, context: Dict[str, Any] = None) -> SentimentResult:
        """Analyze sentiment of text"""
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        # Count positive and negative words
        positive_count = sum(1 for word in words if word in self.positive_words)
        negative_count = sum(1 for word in words if word in self.negative_words)
        
        total_words = len(words)
        if total_words == 0:
            total_words = 1
        
        # Calculate scores
        positive_score = positive_count / total_words
        negative_score = negative_count / total_words
        neutral_score = 1.0 - (positive_score + negative_score)
        
        # Calculate intensity
        intensity = (positive_score - negative_score) * 2.0
        intensity = max(-1.0, min(1.0, intensity))
        
        # Determine sentiment
        if intensity > 0.3:
            sentiment = Sentiment.POSITIVE
        elif intensity < -0.3:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.NEUTRAL
        
        # Calculate confidence based on word count and sentiment strength
        confidence = min(0.5 + (total_words * 0.01) + abs(intensity) * 0.3, 1.0)
        
        # Detect emotions
        emotions = self._detect_emotions(text_lower)
        
        result = SentimentResult(
            sentiment=sentiment,
            intensity=intensity,
            confidence=confidence,
            positive_score=positive_score,
            negative_score=negative_score,
            neutral_score=neutral_score,
            emotions=emotions,
            metadata={"context": context or {}}
        )
        
        # Record in history
        self.analysis_counter += 1
        self.analysis_history.append({
            "text": text,
            "result": result.to_dict(),
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info(f"Analyzed sentiment: {sentiment.value} (intensity: {intensity:.2f})")
        return result
    
    def _detect_emotions(self, text: str) -> Dict[str, float]:
        """Detect emotions in text"""
        emotion_scores = defaultdict(float)
        
        for emotion, emotion_words in self.emotion_lexicon.items():
            count = sum(1 for word in emotion_words if word in text)
            if count > 0:
                emotion_scores[emotion] = min(count * 0.2, 1.0)
        
        return dict(emotion_scores)
    
    def analyze_sentiment_batch(self, texts: List[str]) -> List[SentimentResult]:
        """Analyze sentiment for multiple texts"""
        return [self.analyze_sentiment(text) for text in texts]
    
    def get_sentiment_stats(self) -> Dict[str, Any]:
        """Get statistics about sentiment analysis"""
        sentiment_counts = defaultdict(int)
        intensity_sum = defaultdict(float)
        
        for entry in self.analysis_history:
            sentiment = entry["result"]["sentiment"]
            intensity = entry["result"]["intensity"]
            sentiment_counts[sentiment] += 1
            intensity_sum[sentiment] += intensity
        
        avg_intensity = {}
        for sentiment in sentiment_counts:
            avg_intensity[sentiment] = intensity_sum[sentiment] / sentiment_counts[sentiment]
        
        return {
            "total_analyses": self.analysis_counter,
            "sentiment_distribution": dict(sentiment_counts),
            "average_intensity": avg_intensity,
            "positive_words": len(self.positive_words),
            "negative_words": len(self.negative_words),
            "emotions": len(self.emotion_lexicon)
        }
    
    async def health_check(self) -> str:
        """Health check for the sentiment analysis system"""
        stats = self.get_sentiment_stats()
        return f"healthy ({stats['positive_words']} positive words, {stats['negative_words']} negative words, {stats['total_analyses']} analyses)"
    
    async def shutdown(self):
        """Shutdown the sentiment analysis system"""
        logger.info("Sentiment analysis system shutting down")
