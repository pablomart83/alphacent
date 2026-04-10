#!/usr/bin/env python3
"""
Test script to compare JSON generation quality across different Ollama models.
"""

import json
import sys
import time
from typing import Dict, List

import requests


def test_model_json_quality(model: str, base_url: str = "http://localhost:11434") -> Dict:
    """
    Test a model's ability to generate valid JSON.
    
    Args:
        model: Model name to test
        base_url: Ollama API endpoint
    
    Returns:
        Dictionary with test results
    """
    prompt = """Generate a trading strategy in JSON format. Respond with ONLY valid JSON, no other text.

{
    "name": "Strategy name",
    "description": "Strategy description",
    "rules": {
        "entry_conditions": ["condition 1", "condition 2"],
        "exit_conditions": ["condition 1", "condition 2"],
        "indicators": ["indicator 1"],
        "timeframe": "1d"
    },
    "symbols": ["AAPL", "MSFT"],
    "risk_params": {
        "max_position_size_pct": 0.1,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04
    }
}

Generate a momentum strategy following this exact format."""

    print(f"\nTesting model: {model}")
    print("-" * 60)
    
    results = {
        "model": model,
        "attempts": 3,
        "successes": 0,
        "failures": 0,
        "avg_time": 0,
        "errors": []
    }
    
    total_time = 0
    
    for attempt in range(3):
        try:
            start_time = time.time()
            
            # Call Ollama API
            response = requests.post(
                f"{base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 500
                    }
                },
                timeout=30
            )
            
            elapsed = time.time() - start_time
            total_time += elapsed
            
            if response.status_code != 200:
                results["failures"] += 1
                results["errors"].append(f"HTTP {response.status_code}")
                print(f"  Attempt {attempt + 1}: ✗ HTTP Error {response.status_code}")
                continue
            
            # Extract response
            response_text = response.json().get("response", "")
            
            # Try to parse JSON
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                results["failures"] += 1
                results["errors"].append("No JSON found")
                print(f"  Attempt {attempt + 1}: ✗ No JSON found ({elapsed:.2f}s)")
                continue
            
            json_str = json_match.group(0)
            
            # Try to parse
            try:
                data = json.loads(json_str)
                results["successes"] += 1
                print(f"  Attempt {attempt + 1}: ✓ Valid JSON ({elapsed:.2f}s)")
            except json.JSONDecodeError as e:
                results["failures"] += 1
                results["errors"].append(f"JSON parse error: {str(e)[:50]}")
                print(f"  Attempt {attempt + 1}: ✗ Invalid JSON ({elapsed:.2f}s)")
        
        except requests.exceptions.Timeout:
            results["failures"] += 1
            results["errors"].append("Timeout")
            print(f"  Attempt {attempt + 1}: ✗ Timeout")
        
        except Exception as e:
            results["failures"] += 1
            results["errors"].append(str(e)[:50])
            print(f"  Attempt {attempt + 1}: ✗ Error: {e}")
    
    results["avg_time"] = total_time / 3
    results["success_rate"] = (results["successes"] / results["attempts"]) * 100
    
    print(f"\nResults:")
    print(f"  Success rate: {results['success_rate']:.0f}% ({results['successes']}/{results['attempts']})")
    print(f"  Average time: {results['avg_time']:.2f}s")
    
    return results


def get_available_models(base_url: str = "http://localhost:11434") -> List[str]:
    """Get list of available Ollama models."""
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
        models = [model['name'] for model in response.json().get('models', [])]
        return models
    except Exception as e:
        print(f"Error getting models: {e}")
        return []


def main():
    """Main test function."""
    print("=" * 60)
    print("Ollama Model JSON Quality Test")
    print("=" * 60)
    
    # Get available models
    available_models = get_available_models()
    
    if not available_models:
        print("No Ollama models found. Please install Ollama and pull a model.")
        sys.exit(1)
    
    print(f"\nAvailable models: {', '.join(available_models)}")
    
    # Test models in order of preference
    test_models = [
        "qwen2.5-coder:7b",
        "llama3.1:8b",
        "mistral:7b",
        "llama3.2:3b",
        "llama3.2:1b"
    ]
    
    results = []
    for model in test_models:
        if model in available_models:
            result = test_model_json_quality(model)
            results.append(result)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"\n{'Model':<25} {'Success Rate':<15} {'Avg Time':<10}")
    print("-" * 60)
    
    for result in sorted(results, key=lambda x: x['success_rate'], reverse=True):
        print(f"{result['model']:<25} {result['success_rate']:>6.0f}% ({result['successes']}/{result['attempts']})      {result['avg_time']:>6.2f}s")
    
    print("\n" + "=" * 60)
    print("Recommendation")
    print("=" * 60)
    
    best = max(results, key=lambda x: x['success_rate'])
    print(f"\nBest model: {best['model']}")
    print(f"  - Success rate: {best['success_rate']:.0f}%")
    print(f"  - Average time: {best['avg_time']:.2f}s")
    
    if best['success_rate'] < 80:
        print("\n⚠️  Warning: Even the best available model has low success rate.")
        print("   Consider installing a better model:")
        print("   - ollama pull qwen2.5-coder:7b (Recommended)")
        print("   - ollama pull llama3.2:3b (Quick upgrade)")
        print("   - ollama pull llama3.1:8b (Best quality)")
    
    print(f"\nTo use this model, run:")
    print(f"  export OLLAMA_MODEL=\"{best['model']}\"")
    print()


if __name__ == "__main__":
    main()
