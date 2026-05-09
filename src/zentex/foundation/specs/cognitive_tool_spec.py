"""Abstract specs for cognitive tools used in reasoning pipelines."""

from abc import ABC, abstractmethod


class CognitiveToolSpec(ABC):
    """Base contract for all cognitive tools."""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the unique name identifier for this cognitive tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of what this tool does."""
        ...

    @abstractmethod
    def input_schema(self) -> dict:
        """Return a JSON schema dict describing the expected input format."""
        ...

    @abstractmethod
    def output_schema(self) -> dict:
        """Return a JSON schema dict describing the expected output format."""
        ...

    @abstractmethod
    def invoke(self, inputs: dict) -> dict:
        """Invoke the tool with the given inputs and return the output dict."""
        ...


class LogicalCognitiveToolSpec(CognitiveToolSpec):
    """Extended contract for cognitive tools that expose explicit reasoning chains."""

    @abstractmethod
    def reasoning_chain(self, inputs: dict) -> list[str]:
        """Return an ordered list of reasoning steps produced for the given inputs."""
        ...

    @abstractmethod
    def invoke_with_reasoning(self, inputs: dict) -> tuple[dict, list[str]]:
        """Invoke the tool and return both the output and the reasoning steps.

        Returns:
            A tuple of (output_dict, reasoning_steps) where reasoning_steps is
            the ordered list returned by reasoning_chain.
        """
        ...
