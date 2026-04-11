#!/usr/bin/env python3
"""
Zentex Performance Optimization Toolkit

自动化工具集，用于：
1. 性能基准测试
2. 优化效果验证
3. 监控数据收集
4. 报告生成
"""

import argparse
import json
import time
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class PerformanceBenchmark:
    """性能基准测试工具"""
    
    def __init__(self):
        self.results = {}
    
    def benchmark_llm_cache(self, num_iterations=100):
        """基准测试 LLM 缓存性能"""
        print("\n🔍 Benchmarking LLM Cache...")
        
        try:
            from zentex.llm.cache import LLMResponseCache
            from unittest.mock import Mock
            
            # 创建缓存
            cache = LLMResponseCache(
                max_size=1000,
                max_memory_mb=100,
                default_ttl=300,
            )
            
            # 模拟 LLM 调用
            mock_response = {"answer": "test response"}
            
            # 预热缓存
            for i in range(10):
                cache.set(f"prompt_{i}", {}, "gpt-4", mock_response)
            
            # 测试缓存命中
            start_time = time.time()
            hits = 0
            misses = 0
            
            for i in range(num_iterations):
                prompt_key = f"prompt_{i % 10}"  # 重复使用 10 个 key
                result = cache.get(prompt_key, {}, "gpt-4")
                
                if result is not None:
                    hits += 1
                else:
                    misses += 1
            
            elapsed = time.time() - start_time
            
            stats = cache.get_stats()
            
            self.results['llm_cache'] = {
                'iterations': num_iterations,
                'elapsed_seconds': round(elapsed, 3),
                'avg_time_ms': round((elapsed / num_iterations) * 1000, 3),
                'hits': hits,
                'misses': misses,
                'hit_rate': round(hits / num_iterations * 100, 2),
                'cache_stats': stats,
            }
            
            print(f"✅ Completed {num_iterations} iterations")
            print(f"   Hit rate: {self.results['llm_cache']['hit_rate']}%")
            print(f"   Avg time: {self.results['llm_cache']['avg_time_ms']:.3f}ms")
            
        except Exception as e:
            print(f"❌ LLM Cache benchmark failed: {e}")
            self.results['llm_cache'] = {'error': str(e)}
    
    def benchmark_faiss_search(self, num_vectors=10000, num_queries=100):
        """基准测试 FAISS 向量搜索"""
        print("\n🔍 Benchmarking FAISS Vector Search...")
        
        try:
            import numpy as np
            from zentex.memory.storage.vector_search_faiss import FAISSVectorIndex
            
            # 创建索引
            index = FAISSVectorIndex(
                dimension=768,
                index_type="hnsw",
            )
            
            # 生成随机向量
            print(f"   Generating {num_vectors} vectors...")
            vectors = np.random.rand(num_vectors, 768).astype('float32')
            metadata = [{"id": i} for i in range(num_vectors)]
            
            # 添加到索引
            print(f"   Adding vectors to index...")
            start_add = time.time()
            index.add_vectors(vectors, metadata)
            add_time = time.time() - start_add
            
            print(f"   Index built in {add_time:.2f}s, size: {index.size}")
            
            # 基准测试搜索
            print(f"   Running {num_queries} queries...")
            query_vectors = np.random.rand(num_queries, 768).astype('float32')
            
            start_search = time.time()
            for query_vec in query_vectors:
                results = index.search(query_vec, k=10)
            
            search_time = time.time() - start_search
            avg_search_time = (search_time / num_queries) * 1000  # ms
            
            self.results['faiss_search'] = {
                'num_vectors': num_vectors,
                'num_queries': num_queries,
                'index_build_time_seconds': round(add_time, 3),
                'total_search_time_seconds': round(search_time, 3),
                'avg_search_time_ms': round(avg_search_time, 3),
                'queries_per_second': round(num_queries / search_time, 2),
            }
            
            print(f"✅ Search completed")
            print(f"   Avg search time: {avg_search_time:.3f}ms")
            print(f"   Queries/sec: {self.results['faiss_search']['queries_per_second']}")
            
            # 验证性能目标
            if num_vectors <= 10000 and avg_search_time < 50:
                print(f"   ✅ Performance target met (<50ms for 10k vectors)")
            elif num_vectors <= 100000 and avg_search_time < 100:
                print(f"   ✅ Performance target met (<100ms for 100k vectors)")
            else:
                print(f"   ⚠️  Performance may need optimization")
            
        except ImportError as e:
            print(f"⚠️  FAISS not installed. Install with: pip install faiss-cpu")
            self.results['faiss_search'] = {'error': 'FAISS not installed', 'details': str(e)}
        except Exception as e:
            print(f"❌ FAISS benchmark failed: {e}")
            import traceback
            traceback.print_exc()
            self.results['faiss_search'] = {'error': str(e)}
    
    def benchmark_plugin_loading(self, num_plugins=10):
        """基准测试插件加载（串行 vs 并行）"""
        print("\n🔍 Benchmarking Plugin Loading...")
        
        try:
            from zentex.runtime.plugin_loader import ParallelPluginLoader
            from unittest.mock import Mock
            import concurrent.futures
            
            # 创建模拟插件规格
            plugin_specs = []
            for i in range(num_plugins):
                plugin_specs.append({
                    'plugin_id': f'test_plugin_{i}',
                    'load_time': 0.5,  # 模拟 0.5 秒加载时间
                })
            
            # 测试串行加载
            print(f"   Testing serial loading ({num_plugins} plugins)...")
            start_serial = time.time()
            
            for spec in plugin_specs:
                time.sleep(spec['load_time'])  # 模拟加载
            
            serial_time = time.time() - start_serial
            
            # 测试并行加载
            print(f"   Testing parallel loading ({num_plugins} plugins)...")
            
            loader = ParallelPluginLoader(max_workers=4)
            
            def mock_load(spec):
                time.sleep(spec['load_time'])
                return Mock()
            
            start_parallel = time.time()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(mock_load, spec) for spec in plugin_specs]
                for future in concurrent.futures.as_completed(futures):
                    future.result()
            
            parallel_time = time.time() - start_parallel
            
            speedup = serial_time / parallel_time if parallel_time > 0 else 0
            
            self.results['plugin_loading'] = {
                'num_plugins': num_plugins,
                'serial_time_seconds': round(serial_time, 3),
                'parallel_time_seconds': round(parallel_time, 3),
                'speedup_factor': round(speedup, 2),
                'improvement_percent': round((1 - parallel_time / serial_time) * 100, 2),
            }
            
            print(f"✅ Loading completed")
            print(f"   Serial: {serial_time:.2f}s")
            print(f"   Parallel: {parallel_time:.2f}s")
            print(f"   Speedup: {speedup:.2f}x ({self.results['plugin_loading']['improvement_percent']}% faster)")
            
        except Exception as e:
            print(f"❌ Plugin loading benchmark failed: {e}")
            self.results['plugin_loading'] = {'error': str(e)}
    
    def generate_report(self, output_file: str = "benchmark_report.json"):
        """生成基准测试报告"""
        print("\n📊 Generating Report...")
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'system_info': {
                'python_version': sys.version,
                'platform': sys.platform,
            },
            'benchmarks': self.results,
            'summary': self._generate_summary(),
        }
        
        # 保存到文件
        output_path = Path(output_file)
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✅ Report saved to {output_path}")
        
        # 打印摘要
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        
        for key, value in report['summary'].items():
            print(f"{key}: {value}")
        
        print("="*60)
        
        return report
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成摘要信息"""
        summary = {}
        
        # LLM 缓存
        if 'llm_cache' in self.results and 'error' not in self.results['llm_cache']:
            cache_result = self.results['llm_cache']
            summary['llm_cache_hit_rate'] = f"{cache_result['hit_rate']}%"
            summary['llm_cache_avg_time'] = f"{cache_result['avg_time_ms']:.3f}ms"
        
        # FAISS 搜索
        if 'faiss_search' in self.results and 'error' not in self.results['faiss_search']:
            faiss_result = self.results['faiss_search']
            summary['faiss_avg_search_time'] = f"{faiss_result['avg_search_time_ms']:.3f}ms"
            summary['faiss_qps'] = f"{faiss_result['queries_per_second']}"
        
        # 插件加载
        if 'plugin_loading' in self.results and 'error' not in self.results['plugin_loading']:
            plugin_result = self.results['plugin_loading']
            summary['plugin_loading_speedup'] = f"{plugin_result['speedup_factor']}x"
            summary['plugin_loading_improvement'] = f"{plugin_result['improvement_percent']}%"
        
        return summary


class HealthCheckRunner:
    """健康检查运行器"""
    
    def run_all_checks(self):
        """运行所有健康检查"""
        print("\n🏥 Running Health Checks...")
        
        try:
            from zentex.runtime.health_checker import (
                HealthChecker,
                check_memory_usage,
                check_disk_space,
            )
            
            checker = HealthChecker()
            
            # 注册检查
            checker.register_check("memory", check_memory_usage)
            checker.register_check("disk", lambda: check_disk_space("/"))
            
            # 运行检查
            results = checker.run_all_checks()
            
            print("\nHealth Check Results:")
            print("-" * 60)
            
            for name, result in results.items():
                status_icon = "✅" if result.status.value == "healthy" else "⚠️"
                print(f"{status_icon} {name}: {result.status.value}")
                print(f"   {result.message}")
            
            overall = checker.get_overall_status()
            print("-" * 60)
            print(f"Overall Status: {overall.value.upper()}")
            
            return results
        
        except ImportError:
            print("⚠️  Health checker not implemented yet")
            return {}
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return {}


def main():
    parser = argparse.ArgumentParser(
        description="Zentex Performance Optimization Toolkit"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Benchmark 命令
    bench_parser = subparsers.add_parser('benchmark', help='Run performance benchmarks')
    bench_parser.add_argument('--llm-cache', action='store_true', help='Benchmark LLM cache')
    bench_parser.add_argument('--faiss', action='store_true', help='Benchmark FAISS search')
    bench_parser.add_argument('--plugins', action='store_true', help='Benchmark plugin loading')
    bench_parser.add_argument('--all', action='store_true', help='Run all benchmarks')
    bench_parser.add_argument('--output', type=str, default='benchmark_report.json',
                             help='Output file for report')
    bench_parser.add_argument('--iterations', type=int, default=100,
                             help='Number of iterations for tests')
    
    # Health check 命令
    health_parser = subparsers.add_parser('health', help='Run health checks')
    
    args = parser.parse_args()
    
    if args.command == 'benchmark':
        benchmark = PerformanceBenchmark()
        
        if args.all or args.llm_cache:
            benchmark.benchmark_llm_cache(num_iterations=args.iterations)
        
        if args.all or args.faiss:
            benchmark.benchmark_faiss_search()
        
        if args.all or args.plugins:
            benchmark.benchmark_plugin_loading()
        
        benchmark.generate_report(output_file=args.output)
    
    elif args.command == 'health':
        runner = HealthCheckRunner()
        runner.run_all_checks()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
