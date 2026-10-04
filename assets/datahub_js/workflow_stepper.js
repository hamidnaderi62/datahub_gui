(function () {
  'use strict';

  const wizard = document.querySelector('.wizard-numbered');
  if (!wizard || typeof Stepper === 'undefined') return;

    const stepper = new Stepper(wizard, { linear: true });
    let currentStep = 1;
    window.DataHubWorkflowNext = function () {
      stepper.next();
      currentStep = Math.min(currentStep + 1, wizard.querySelectorAll('.step').length);
    };
    wizard.querySelectorAll('.btn-next').forEach(button => {
      button.addEventListener('click', () => {
        if (typeof window.DataHubWorkflowValidateStep === 'function' && !window.DataHubWorkflowValidateStep(currentStep)) return;
        window.DataHubWorkflowNext();
      });
    });
    wizard.querySelectorAll('.btn-prev').forEach(button => {
      button.addEventListener('click', () => {
        stepper.previous();
        currentStep = Math.max(currentStep - 1, 1);
      });
  });

  // Expose the instance for page-specific validation and integration tests.
  window.dataHubStepper = stepper;
})();
