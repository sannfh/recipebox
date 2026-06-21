class AppError(Exception):
    """Base for all domain errors."""


class NotFoundError(AppError):
    pass


class ConflictError(AppError):
    pass


class UnauthorizedError(AppError):
    pass


class RecipeNotFoundError(NotFoundError):
    pass


class DuplicateEmailError(ConflictError):
    pass


class AuthenticationError(UnauthorizedError):
    pass


class ForbiddenError(AppError):
    pass


class RecipeImportError(AppError):
    pass


class PantryItemNotFoundError(NotFoundError):
    pass


class DuplicatePantryItemError(ConflictError):
    pass
