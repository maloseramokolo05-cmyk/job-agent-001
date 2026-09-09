from abc import ABC, abstractmethod
class JobSource(ABC):
 name="base"
 @abstractmethod
 def search(self, profile, preferences): ...
