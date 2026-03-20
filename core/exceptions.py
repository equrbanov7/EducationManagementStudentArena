"""
Core exceptions for EMS Arena project.
Custom exception classes for application-specific errors.
"""


class EMSArenaException(Exception):
    """
    Base exception class for EMS Arena application.
    """


class PermissionDenied(EMSArenaException):
    """
    Exception raised when user doesn't have permission for an action.
    """


class InvalidOperation(EMSArenaException):
    """
    Exception raised when an invalid operation is attempted.
    """
