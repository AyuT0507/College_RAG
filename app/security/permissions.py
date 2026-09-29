from enum import StrEnum


class Role(StrEnum):
    STUDENT = "student"
    FACULTY = "faculty"
    MANAGEMENT = "management"
    ADMIN = "admin"


ROLE_UPLOAD = {Role.FACULTY, Role.MANAGEMENT, Role.ADMIN}
ROLE_CRAWL = {Role.ADMIN, Role.MANAGEMENT}
