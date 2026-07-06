"""
Test suite for Phase 2 - Natural Language Understanding components
"""

import asyncio
import sys

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.nlu import (
    IntentRecognizer, Intent,
    EntityExtractor, EntityType,
    SentimentAnalyzer, Sentiment
)


async def test_intent_recognition():
    """Test the intent recognition system"""
    print("\n" + "="*60)
    print("Testing Intent Recognition System")
    print("="*60)
    
    recognizer = IntentRecognizer()
    
    # Test 1: Query intent
    print("\n1. Testing query intent...")
    result = recognizer.recognize_intent("What is the weather today?")
    print(f"   ✓ Intent: {result.intent.value}")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.intent == Intent.QUERY
    
    # Test 2: Command intent
    print("\n2. Testing command intent...")
    result = recognizer.recognize_intent("Run the backup script")
    print(f"   ✓ Intent: {result.intent.value}")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.intent == Intent.COMMAND
    
    # Test 3: Task intent
    print("\n3. Testing task intent...")
    result = recognizer.recognize_intent("Help me analyze the codebase")
    print(f"   ✓ Intent: {result.intent.value}")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.intent == Intent.TASK
    
    # Test 4: Analysis intent
    print("\n4. Testing analysis intent...")
    result = recognizer.recognize_intent("Analyze the performance metrics")
    print(f"   ✓ Intent: {result.intent.value}")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.intent == Intent.ANALYSIS
    
    # Test 5: Planning intent
    print("\n5. Testing planning intent...")
    result = recognizer.recognize_intent("Plan the deployment strategy")
    print(f"   ✓ Intent: {result.intent.value}")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.intent == Intent.PLANNING
    
    # Test 6: Reflection intent
    print("\n6. Testing reflection intent...")
    result = recognizer.recognize_intent("Reflect on the last deployment")
    print(f"   ✓ Intent: {result.intent.value}")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.intent == Intent.REFLECTION
    
    # Test 7: Conversation intent
    print("\n7. Testing conversation intent...")
    result = recognizer.recognize_intent("Hello Jarvis")
    print(f"   ✓ Intent: {result.intent.value}")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.intent == Intent.CONVERSATION
    
    # Test 8: Entity extraction in intent
    print("\n8. Testing entity extraction...")
    result = recognizer.recognize_intent("Show me the file app.py")
    print(f"   ✓ Entities: {result.entities}")
    assert "file_path" in result.entities
    
    # Test 9: Custom pattern
    print("\n9. Testing custom pattern...")
    recognizer.add_pattern(
        intent=Intent.COMMAND,
        patterns=[r"deploy"],
        examples=["Deploy to production"]
    )
    result = recognizer.recognize_intent("Deploy to production")
    print(f"   ✓ Custom pattern recognized: {result.intent.value}")
    assert result.intent == Intent.COMMAND
    
    # Test 10: Recognition stats
    print("\n10. Testing recognition statistics...")
    stats = recognizer.get_recognition_stats()
    print(f"   ✓ Total recognitions: {stats['total_recognitions']}")
    print(f"   ✓ Total patterns: {stats['total_patterns']}")
    
    print("\n✅ Intent Recognition tests passed")
    return True


async def test_entity_extraction():
    """Test the entity extraction system"""
    print("\n" + "="*60)
    print("Testing Entity Extraction System")
    print("="*60)
    
    extractor = EntityExtractor()
    
    # Test 1: Email extraction
    print("\n1. Testing email extraction...")
    text = "Contact me at user@example.com for more info"
    entities = extractor.extract_entities(text)
    email_entities = [e for e in entities if e.entity_type == EntityType.EMAIL]
    print(f"   ✓ Emails found: {len(email_entities)}")
    assert len(email_entities) > 0
    
    # Test 2: URL extraction
    print("\n2. Testing URL extraction...")
    text = "Visit https://example.com for documentation"
    entities = extractor.extract_entities(text)
    url_entities = [e for e in entities if e.entity_type == EntityType.URL]
    print(f"   ✓ URLs found: {len(url_entities)}")
    assert len(url_entities) > 0
    
    # Test 3: File path extraction
    print("\n3. Testing file path extraction...")
    text = "Check the file app.py for the main logic"
    entities = extractor.extract_entities(text)
    file_entities = [e for e in entities if e.entity_type == EntityType.FILE_PATH]
    print(f"   ✓ File paths found: {len(file_entities)}")
    assert len(file_entities) > 0
    
    # Test 4: Number extraction
    print("\n4. Testing number extraction...")
    text = "There are 42 items in the list"
    entities = extractor.extract_entities(text)
    number_entities = [e for e in entities if e.entity_type == EntityType.NUMBER]
    print(f"   ✓ Numbers found: {len(number_entities)}")
    assert len(number_entities) > 0
    
    # Test 5: Command extraction
    print("\n5. Testing command extraction...")
    text = "Run git status to check changes"
    entities = extractor.extract_entities(text)
    command_entities = [e for e in entities if e.entity_type == EntityType.COMMAND]
    print(f"   ✓ Commands found: {len(command_entities)}")
    assert len(command_entities) > 0
    
    # Test 6: Function extraction
    print("\n6. Testing function extraction...")
    text = "Call the function main() to start the app"
    entities = extractor.extract_entities(text)
    function_entities = [e for e in entities if e.entity_type == EntityType.FUNCTION]
    print(f"   ✓ Functions found: {len(function_entities)}")
    assert len(function_entities) > 0
    
    # Test 7: Custom entity
    print("\n7. Testing custom entity...")
    extractor.add_custom_entity(EntityType.PERSON, ["John", "Jane", "Bob"])
    text = "John and Jane are working on the project"
    entities = extractor.extract_entities(text)
    person_entities = [e for e in entities if e.entity_type == EntityType.PERSON]
    print(f"   ✓ Custom entities found: {len(person_entities)}")
    assert len(person_entities) > 0
    
    # Test 8: Entity summary
    print("\n8. Testing entity summary...")
    text = "Email user@example.com and visit https://example.com"
    summary = extractor.get_entity_summary(text)
    print(f"   ✓ Total entities: {summary['total_entities']}")
    print(f"   ✓ By type: {summary['by_type']}")
    
    # Test 9: Extraction by type
    print("\n9. Testing extraction by type...")
    text = "Contact user@example.com or admin@example.com"
    emails = extractor.extract_entities_by_type(text, EntityType.EMAIL)
    print(f"   ✓ Emails by type: {len(emails)}")
    assert len(emails) > 0
    
    # Test 10: Extraction stats
    print("\n10. Testing extraction statistics...")
    stats = extractor.get_extraction_stats()
    print(f"   ✓ Total extractions: {stats['total_extractions']}")
    print(f"   ✓ Total patterns: {stats['total_patterns']}")
    
    print("\n✅ Entity Extraction tests passed")
    return True


async def test_sentiment_analysis():
    """Test the sentiment analysis system"""
    print("\n" + "="*60)
    print("Testing Sentiment Analysis System")
    print("="*60)
    
    analyzer = SentimentAnalyzer()
    
    # Test 1: Positive sentiment
    print("\n1. Testing positive sentiment...")
    result = analyzer.analyze_sentiment("This is a great solution, I love it!")
    print(f"   ✓ Sentiment: {result.sentiment.value}")
    print(f"   ✓ Intensity: {result.intensity:.2f}")
    assert result.sentiment == Sentiment.POSITIVE
    assert result.intensity > 0
    
    # Test 2: Negative sentiment
    print("\n2. Testing negative sentiment...")
    result = analyzer.analyze_sentiment("This is terrible, I hate it!")
    print(f"   ✓ Sentiment: {result.sentiment.value}")
    print(f"   ✓ Intensity: {result.intensity:.2f}")
    assert result.sentiment == Sentiment.NEGATIVE
    assert result.intensity < 0
    
    # Test 3: Neutral sentiment
    print("\n3. Testing neutral sentiment...")
    result = analyzer.analyze_sentiment("The file is located at /path/to/file")
    print(f"   ✓ Sentiment: {result.sentiment.value}")
    print(f"   ✓ Intensity: {result.intensity:.2f}")
    assert result.sentiment == Sentiment.NEUTRAL
    
    # Test 4: Emotion detection
    print("\n4. Testing emotion detection...")
    result = analyzer.analyze_sentiment("I am happy and excited about this!")
    print(f"   ✓ Emotions: {result.emotions}")
    assert len(result.emotions) > 0
    
    # Test 5: Custom sentiment words
    print("\n5. Testing custom sentiment words...")
    analyzer.add_sentiment_words(positive=["fantastic", "superb"])
    result = analyzer.analyze_sentiment("This is fantastic and superb!")
    print(f"   ✓ Sentiment with custom words: {result.sentiment.value}")
    assert result.sentiment == Sentiment.POSITIVE
    
    # Test 6: Batch analysis
    print("\n6. Testing batch analysis...")
    texts = [
        "This is great",
        "This is bad",
        "This is okay"
    ]
    results = analyzer.analyze_sentiment_batch(texts)
    print(f"   ✓ Batch results: {len(results)}")
    assert len(results) == 3
    
    # Test 7: Confidence calculation
    print("\n7. Testing confidence calculation...")
    result = analyzer.analyze_sentiment("This is a very good and excellent solution with amazing features")
    print(f"   ✓ Confidence: {result.confidence:.2f}")
    assert result.confidence > 0.5
    
    # Test 8: Sentiment stats
    print("\n8. Testing sentiment statistics...")
    stats = analyzer.get_sentiment_stats()
    print(f"   ✓ Total analyses: {stats['total_analyses']}")
    print(f"   ✓ Positive words: {stats['positive_words']}")
    print(f"   ✓ Negative words: {stats['negative_words']}")
    
    # Test 9: Score breakdown
    print("\n9. Testing score breakdown...")
    result = analyzer.analyze_sentiment("Good but some issues")
    print(f"   ✓ Positive score: {result.positive_score:.2f}")
    print(f"   ✓ Negative score: {result.negative_score:.2f}")
    print(f"   ✓ Neutral score: {result.neutral_score:.2f}")
    
    # Test 10: Health check
    print("\n10. Testing health check...")
    health = await analyzer.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Sentiment Analysis tests passed")
    return True


async def test_nlu_integration():
    """Test NLU component integration"""
    print("\n" + "="*60)
    print("Testing NLU Integration")
    print("="*60)
    
    recognizer = IntentRecognizer()
    extractor = EntityExtractor()
    analyzer = SentimentAnalyzer()
    
    # Test 1: Full NLU pipeline
    print("\n1. Testing full NLU pipeline...")
    text = "Please analyze the file app.py, it's really important"
    
    # Recognize intent
    intent = recognizer.recognize_intent(text)
    print(f"   ✓ Intent: {intent.intent.value}")
    
    # Extract entities
    entities = extractor.extract_entities(text)
    print(f"   ✓ Entities: {len(entities)}")
    
    # Analyze sentiment
    sentiment = analyzer.analyze_sentiment(text)
    print(f"   ✓ Sentiment: {sentiment.sentiment.value}")
    
    # Test 2: Context-aware processing
    print("\n2. Testing context-aware processing...")
    context = {"user": "developer", "task": "code_review"}
    intent = recognizer.recognize_intent("Show me the errors", context=context)
    print(f"   ✓ Context: {intent.metadata}")
    
    # Test 3: Multi-entity extraction
    print("\n3. Testing multi-entity extraction...")
    text = "Email john@example.com about the file test.py at 5:00 PM"
    entities = extractor.extract_entities(text)
    entity_types = set(e.entity_type.value for e in entities)
    print(f"   ✓ Entity types: {entity_types}")
    
    # Test 4: Sentiment with entities
    print("\n4. Testing sentiment with entities...")
    text = "I love the new feature in app.py"
    sentiment = analyzer.analyze_sentiment(text)
    entities = extractor.extract_entities(text)
    print(f"   ✓ Sentiment: {sentiment.sentiment.value}")
    print(f"   ✓ Entities: {len(entities)}")
    
    # Test 5: Cross-component stats
    print("\n5. Testing cross-component statistics...")
    intent_stats = recognizer.get_recognition_stats()
    entity_stats = extractor.get_extraction_stats()
    sentiment_stats = analyzer.get_sentiment_stats()
    
    print(f"   ✓ Intent recognitions: {intent_stats['total_recognitions']}")
    print(f"   ✓ Entity extractions: {entity_stats['total_extractions']}")
    print(f"   ✓ Sentiment analyses: {sentiment_stats['total_analyses']}")
    
    print("\n✅ NLU Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 2 Week 1 tests"""
    print("\n" + "="*60)
    print("PHASE 2 WEEK 1 - NATURAL LANGUAGE UNDERSTANDING TESTS")
    print("="*60)
    
    results = {}
    
    try:
        results['intent_recognition'] = await test_intent_recognition()
    except Exception as e:
        print(f"\n❌ Intent recognition tests failed: {e}")
        results['intent_recognition'] = False
    
    try:
        results['entity_extraction'] = await test_entity_extraction()
    except Exception as e:
        print(f"\n❌ Entity extraction tests failed: {e}")
        results['entity_extraction'] = False
    
    try:
        results['sentiment_analysis'] = await test_sentiment_analysis()
    except Exception as e:
        print(f"\n❌ Sentiment analysis tests failed: {e}")
        results['sentiment_analysis'] = False
    
    try:
        results['integration'] = await test_nlu_integration()
    except Exception as e:
        print(f"\n❌ Integration tests failed: {e}")
        results['integration'] = False
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Phase 2 Week 1 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
