"""
Monkey patch for bcrypt to fix compatibility with passlib.

This module adds the __about__ attribute to the bcrypt module that passlib expects
but is missing in newer bcrypt versions (4.0.0+).
"""

import logging

logger = logging.getLogger(__name__)


def apply_bcrypt_patch():
    """
    Apply monkey patch to bcrypt module to make it compatible with passlib.

    This adds the missing __about__ attribute with a __version__ property
    that passlib tries to access.
    """
    try:
        import bcrypt

        # Check if the module already has the attribute to avoid unnecessary patching
        if not hasattr(bcrypt, "__about__"):
            # Create a mock __about__ module with the version attribute
            class About:
                __version__ = getattr(bcrypt, "__version__", "4.3.0")

            # Attach the mock __about__ module to bcrypt
            bcrypt.__about__ = About()

            logger.info(
                f"Successfully patched bcrypt module version {bcrypt.__about__.__version__}"
            )
        else:
            logger.debug(
                "bcrypt module already has __about__ attribute, no patch needed"
            )

    except ImportError:
        logger.warning("Could not import bcrypt module to apply patch")
    except Exception as e:
        logger.error(f"Error applying bcrypt patch: {e}", exc_info=True)


# Apply the patch when this module is imported
apply_bcrypt_patch()
