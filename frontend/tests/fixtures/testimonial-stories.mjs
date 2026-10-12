/** Tests use the same client-approved collection as the public route.
 * Individual checks create malformed or sparse variants locally when needed.
 * This alias is test-only; production never imports the tests directory.
 */
export {clientTestimonials as testimonialStories} from '../../src/site/testimonials-content.mjs';
