from abc import ABC, abstractmethod
from core.models import SharedContext
import logging

class BaseAgent(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def execute(self, context: SharedContext) -> SharedContext:
        """
        Executes the agent's logic. Must return the updated SharedContext.
        """
        pass
