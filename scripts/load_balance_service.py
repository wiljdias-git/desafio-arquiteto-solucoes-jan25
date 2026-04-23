from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from time import perf_counter

import httpx


@dataclass
class LoadResult:
    total_requests: int
    successful_requests: int
    failed_requests: int
    elapsed_seconds: float

    @property
    def loss_percentage(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100

    @property
    def requests_per_second(self) -> float:
        if self.elapsed_seconds == 0:
            return float(self.total_requests)
        return self.total_requests / self.elapsed_seconds


async def execute_load(url: str, total_requests: int, concurrency: int) -> LoadResult:
    semaphore = asyncio.Semaphore(concurrency)
    start_time = perf_counter()

    async with httpx.AsyncClient(timeout=5.0) as client:
        async def single_request() -> bool:
            async with semaphore:
                response = await client.get(url)
                return response.status_code == 200

        results = await asyncio.gather(*(single_request() for _ in range(total_requests)))

    elapsed_seconds = perf_counter() - start_time
    successful_requests = sum(1 for item in results if item)
    failed_requests = total_requests - successful_requests
    return LoadResult(
        total_requests=total_requests,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        elapsed_seconds=elapsed_seconds,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa uma carga simples contra o servico de consolidado diario."
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8001/balances/2026-01-25",
        help="URL de destino para o teste de carga.",
    )
    parser.add_argument(
        "--requests", type=int, default=100, help="Quantidade total de requisicoes."
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
        help="Numero maximo de requisicoes concorrentes.",
    )
    parser.add_argument(
        "--min-rps",
        type=float,
        default=None,
        help="Falha o comando se o throughput observado ficar abaixo deste valor.",
    )
    parser.add_argument(
        "--max-loss-percentage",
        type=float,
        default=None,
        help="Falha o comando se a perda observada ultrapassar este valor.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(execute_load(args.url, args.requests, args.concurrency))
    output = (
        f"total={result.total_requests} "
        f"success={result.successful_requests} "
        f"failed={result.failed_requests} "
        f"loss_percent={result.loss_percentage:.2f} "
        f"rps={result.requests_per_second:.2f}"
    )
    print(output)

    if args.max_loss_percentage is not None and result.loss_percentage > args.max_loss_percentage:
        raise SystemExit(
            (
                "Carga reprovada: "
                f"loss_percent={result.loss_percentage:.2f} "
                f"ultrapassou max_loss_percentage={args.max_loss_percentage:.2f}"
            )
        )

    if args.min_rps is not None and result.requests_per_second < args.min_rps:
        raise SystemExit(
            (
                "Carga reprovada: "
                f"rps={result.requests_per_second:.2f} "
                f"ficou abaixo de min_rps={args.min_rps:.2f}"
            )
        )


if __name__ == "__main__":
    main()
