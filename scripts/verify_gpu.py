#!/usr/bin/env python3
"""Exit unsuccessfully if requested real CUDA inference falls back to CPU."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from app.services.laya_service import LayaService
from scripts.verification_common import STATE, QUESTIONS, assert_gpu, assert_result

def main():
    runtime = {'torch_version': torch.__version__, 'cuda_runtime': torch.version.cuda, 'cuda_available': torch.cuda.is_available(), 'arch_list': torch.cuda.get_arch_list()}
    print(json.dumps({'runtime': runtime}, ensure_ascii=False), flush=True)
    assert runtime['cuda_available'], 'CUDA unavailable'
    runtime.update(gpu_name=torch.cuda.get_device_name(0), capability=list(torch.cuda.get_device_capability(0)))
    x = torch.arange(16, device='cuda', dtype=torch.float32)
    runtime['tensor_sum_squares'] = float((x * x).sum().item())
    assert runtime['tensor_sum_squares'] == 1240
    service = LayaService()
    service.load()
    before = service.info()
    print(json.dumps({'runtime': runtime, 'before': before}, ensure_ascii=False), flush=True)
    assert_gpu(before)
    torch.cuda.reset_peak_memory_stats()
    result = service.predict(STATE, QUESTIONS, max_len=8192)
    print(json.dumps({'result': result, 'after': service.info(), 'peak_allocated_bytes': torch.cuda.max_memory_allocated()}, ensure_ascii=False), flush=True)
    assert_result(result)
    assert_gpu(service.info())

if __name__ == '__main__': main()
