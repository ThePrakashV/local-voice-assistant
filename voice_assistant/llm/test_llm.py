import argparse

from voice_assistant.llm.ollama_client import OllamaClient


def print_stats(stats):
    print(
        f"\n[model={stats['model']} | first token={stats['first_token_latency']}s | "
        f"total={stats['total_time']}s | tokens={stats['tokens']} | "
        f"speed={stats['tokens_per_sec']} tok/s | "
        f"prompt={stats.get('prompt_tokens', 0)} tokens in {stats.get('prompt_eval_time', 0)}s | "
        f"load={stats.get('load_time', 0)}s]"
    )


def ask(client, text):
    print("Assistant: ", end="", flush=True)
    for token in client.chat_stream(text):
        print(token, end="", flush=True)
    print()
    print_stats(client.last_stats)


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant LLM test")
    parser.add_argument("--model", type=str, default=None, help="llama3.2, qwen2.5...")
    parser.add_argument("--prompt", type=str, default=None, help="single question")
    args = parser.parse_args()

    if args.model:
        client = OllamaClient(model=args.model)
    else:
        client = OllamaClient()

    try:
        if args.prompt:
            ask(client, args.prompt)
            return

        print(f"Chat mode (model: {client.model}). 'exit' type panna mudiyum, 'reset' history clear pannum.")
        while True:
            text = input("\nYou: ").strip()
            if not text:
                continue
            if text.lower() == "exit":
                break
            if text.lower() == "reset":
                client.reset()
                print("History clear aachu.")
                continue
            ask(client, text)
    except RuntimeError as error:
        print(f"\nERROR: {error}")


if __name__ == "__main__":
    main()