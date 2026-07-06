"""
Machine Learning Models for Jarvis OS - Phase 2 Component
Simple ML models for prediction and classification
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
import random
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Types of ML models"""
    CLASSIFIER = "classifier"
    REGRESSOR = "regressor"
    CLUSTERING = "clustering"
    ANOMALY_DETECTOR = "anomaly_detector"


class PredictionType(Enum):
    """Types of predictions"""
    BINARY = "binary"
    MULTICLASS = "multiclass"
    NUMERICAL = "numerical"
    CATEGORICAL = "categorical"


@dataclass
class Feature:
    """A feature for ML models"""
    name: str
    value: Any
    weight: float = 1.0
    feature_type: str = "numerical"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "weight": self.weight,
            "feature_type": self.feature_type
        }


@dataclass
class Prediction:
    """A prediction from an ML model"""
    predicted_value: Any
    confidence: float
    model_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicted_value": self.predicted_value,
            "confidence": self.confidence,
            "model_id": self.model_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class TrainingData:
    """Training data for ML models"""
    features: List[Feature]
    label: Any
    weight: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "features": [f.to_dict() for f in self.features],
            "label": self.label,
            "weight": self.weight
        }


class SimpleClassifier:
    """Simple rule-based classifier"""
    
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.rules: List[Dict[str, Any]] = []
        self.feature_importance: Dict[str, float] = defaultdict(float)
        self.prediction_count = 0
        self.accuracy_history: List[float] = []
    
    def add_rule(self, conditions: Dict[str, Any], prediction: Any, confidence: float = 1.0):
        """Add a classification rule"""
        rule = {
            "conditions": conditions,
            "prediction": prediction,
            "confidence": confidence
        }
        self.rules.append(rule)
        logger.debug(f"Added rule to classifier {self.model_id}")
    
    def predict(self, features: List[Feature]) -> Prediction:
        """Make a prediction based on rules"""
        feature_dict = {f.name: f.value for f in features}
        
        # Check each rule
        for rule in self.rules:
            conditions = rule["conditions"]
            match = True
            
            for feature_name, condition_value in conditions.items():
                if feature_name not in feature_dict:
                    match = False
                    break
                
                if isinstance(condition_value, (list, tuple)):
                    if feature_dict[feature_name] not in condition_value:
                        match = False
                        break
                elif feature_dict[feature_name] != condition_value:
                    match = False
                    break
            
            if match:
                self.prediction_count += 1
                return Prediction(
                    predicted_value=rule["prediction"],
                    confidence=rule["confidence"],
                    model_id=self.model_id
                )
        
        # No rule matched
        self.prediction_count += 1
        return Prediction(
            predicted_value="unknown",
            confidence=0.0,
            model_id=self.model_id
        )
    
    def update_feature_importance(self, feature_name: str, importance: float):
        """Update feature importance"""
        self.feature_importance[feature_name] = importance
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get classifier statistics"""
        return {
            "model_id": self.model_id,
            "total_rules": len(self.rules),
            "prediction_count": self.prediction_count,
            "feature_importance": dict(self.feature_importance),
            "average_accuracy": sum(self.accuracy_history) / max(len(self.accuracy_history), 1)
        }


class SimpleRegressor:
    """Simple linear regressor"""
    
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.weights: Dict[str, float] = defaultdict(float)
        self.bias: float = 0.0
        self.prediction_count = 0
        self.error_history: List[float] = []
    
    def train(self, training_data: List[TrainingData], learning_rate: float = 0.01, epochs: int = 100):
        """Train the regressor using gradient descent"""
        logger.info(f"Training regressor {self.model_id} with {len(training_data)} samples")
        
        for epoch in range(epochs):
            total_error = 0.0
            
            for data in training_data:
                feature_dict = {f.name: f.value for f in data.features}
                
                # Make prediction
                prediction = self._predict_raw(feature_dict)
                
                # Calculate error
                error = prediction - data.label
                total_error += error ** 2
                
                # Update weights
                for feature_name, feature_value in feature_dict.items():
                    if isinstance(feature_value, (int, float)):
                        self.weights[feature_name] -= learning_rate * error * feature_value
                
                # Update bias
                self.bias -= learning_rate * error
            
            # Log progress
            if epoch % 10 == 0:
                avg_error = total_error / len(training_data)
                logger.debug(f"Epoch {epoch}, Average Error: {avg_error:.4f}")
        
        logger.info(f"Regressor {self.model_id} training complete")
    
    def _predict_raw(self, feature_dict: Dict[str, Any]) -> float:
        """Raw prediction without confidence"""
        prediction = self.bias
        
        for feature_name, weight in self.weights.items():
            feature_value = feature_dict.get(feature_name, 0.0)
            if isinstance(feature_value, (int, float)):
                prediction += weight * feature_value
        
        return prediction
    
    def predict(self, features: List[Feature]) -> Prediction:
        """Make a prediction"""
        feature_dict = {f.name: f.value for f in features}
        
        prediction = self._predict_raw(feature_dict)
        
        # Calculate confidence based on feature coverage
        covered_features = sum(1 for f in features if f.name in self.weights)
        confidence = min(covered_features / max(len(features), 1), 1.0)
        
        self.prediction_count += 1
        return Prediction(
            predicted_value=prediction,
            confidence=confidence,
            model_id=self.model_id
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get regressor statistics"""
        return {
            "model_id": self.model_id,
            "total_weights": len(self.weights),
            "prediction_count": self.prediction_count,
            "average_error": sum(self.error_history) / max(len(self.error_history), 1),
            "bias": self.bias
        }


class MachineLearningEngine:
    """Machine learning engine for Jarvis OS"""
    
    def __init__(self):
        self.classifiers: Dict[str, SimpleClassifier] = {}
        self.regressors: Dict[str, SimpleRegressor] = {}
        self.model_counter = 0
        self.training_history: List[Dict[str, Any]] = []
        
        logger.info("Machine learning engine initialized")
    
    def create_classifier(self, model_id: Optional[str] = None) -> SimpleClassifier:
        """Create a new classifier"""
        if model_id is None:
            self.model_counter += 1
            model_id = f"classifier_{self.model_counter}"
        
        classifier = SimpleClassifier(model_id)
        self.classifiers[model_id] = classifier
        logger.info(f"Created classifier: {model_id}")
        return classifier
    
    def create_regressor(self, model_id: Optional[str] = None) -> SimpleRegressor:
        """Create a new regressor"""
        if model_id is None:
            self.model_counter += 1
            model_id = f"regressor_{self.model_counter}"
        
        regressor = SimpleRegressor(model_id)
        self.regressors[model_id] = regressor
        logger.info(f"Created regressor: {model_id}")
        return regressor
    
    def get_model(self, model_id: str):
        """Get a model by ID"""
        if model_id in self.classifiers:
            return self.classifiers[model_id]
        elif model_id in self.regressors:
            return self.regressors[model_id]
        else:
            raise ValueError(f"Model {model_id} not found")
    
    def predict(self, model_id: str, features: List[Feature]) -> Prediction:
        """Make a prediction using a model"""
        model = self.get_model(model_id)
        return model.predict(features)
    
    def train_model(self, model_id: str, training_data: List[TrainingData], **kwargs):
        """Train a model"""
        model = self.get_model(model_id)
        
        if isinstance(model, SimpleRegressor):
            model.train(training_data, **kwargs)
            self.training_history.append({
                "model_id": model_id,
                "timestamp": datetime.now().isoformat(),
                "training_samples": len(training_data)
            })
        else:
            logger.warning(f"Training not implemented for model type: {type(model)}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get ML engine statistics"""
        classifier_stats = {model_id: c.get_statistics() 
                          for model_id, c in self.classifiers.items()}
        regressor_stats = {model_id: r.get_statistics() 
                         for model_id, r in self.regressors.items()}
        
        return {
            "total_classifiers": len(self.classifiers),
            "total_regressors": len(self.regressors),
            "classifier_stats": classifier_stats,
            "regressor_stats": regressor_stats,
            "total_training_runs": len(self.training_history)
        }
    
    async def health_check(self) -> str:
        """Health check for the ML engine"""
        stats = self.get_statistics()
        return f"healthy ({stats['total_classifiers']} classifiers, {stats['total_regressors']} regressors)"
    
    async def shutdown(self):
        """Shutdown the ML engine"""
        logger.info("Machine learning engine shutting down")
