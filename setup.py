from setuptools import setup, find_packages

setup(
    name="ShoppingClaw",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "langchain",
        "langchain-ollama",
        "langgraph",
        "python-dotenv",
    ],
)
