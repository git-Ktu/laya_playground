#!/usr/bin/env python3
"""Validate a running real server (default http://127.0.0.1:8000)."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from scripts.verification_common import STATE, QUESTIONS, assert_gpu, assert_result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=180, trust_env=False) as client:
        for path in ['/', '/health', '/info']:
            response = client.get(path)
            response.raise_for_status()
            print(json.dumps({'path': path, 'status': response.status_code, 'body': response.json() if path != '/' else 'Playground HTML'}, ensure_ascii=False))
        assert_gpu(client.get('/info').json())
        response = client.post('/tokenize', json={'state': STATE})
        response.raise_for_status()
        assert response.json()['state_tokens'] > 0
        print(json.dumps({'tokenize': response.json()}, ensure_ascii=False))
        response = client.post('/v1/systemone', json={'state': STATE, 'questions': QUESTIONS, 'max_len': 8192})
        response.raise_for_status()
        result = response.json()
        assert_result(result)
        print(json.dumps({'single': result, 'inference_header': response.headers.get('x-inference-time-ms')}, ensure_ascii=False))
        response = client.post('/v1/systemone/batch', json={'states': [STATE, {'問い合わせ': STATE}], 'questions': QUESTIONS, 'max_len': 8192})
        response.raise_for_status()
        result = response.json()
        assert len(result['results']) == 2
        for item in result['results']: assert_result(item)
        assert 'total_usage' in result
        print(json.dumps({'batch': result}, ensure_ascii=False))
        assert_gpu(client.get('/info').json())

if __name__ == '__main__': main()
