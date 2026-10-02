"""Closed questions copied from the approved brief; profile IDs are host-mapped slots."""

QUESTIONS = {'work_partition.v1': {'type': 'choice',
                       'instructions': 'Which execution partition best fits the summarized work, '
                                       'using only eligible options? Choose insufficient when '
                                       'facts do not distinguish them.',
                       'criteria': {'local': 'The work needs local Codex context or tools '
                                             'throughout.',
                                    'cloud': 'The whole bounded work item fits the approved cloud '
                                             'capability.',
                                    'mixed': 'A separable advisory or research portion fits cloud; '
                                             'execution remains local.',
                                    'insufficient': 'The supplied facts do not support a '
                                                    'partition.'}},
 'host_fit.v1': {'type': 'choice',
                 'instructions': 'Which eligible capability best fits this bounded work item?',
                 'criteria': {'codex': 'Planning, coding, local tools, tests or evidence work.',
                              'chatgpt': 'Self-contained advisory research or prose needing no '
                                         'local tools.',
                              'jev_only': 'One atomic typed semantic judgment with all relevant '
                                          'facts supplied.',
                              'insufficient': 'No supplied capability clearly fits.'}},
 'stall.v1': {'type': 'noul',
              'instructions': 'Do the supplied sanitized progress summaries describe repetition '
                              'without a new useful result?',
              'criteria': {'true': 'The summaries repeat an approach or conclusion without '
                                   'material progress.',
                           'false': 'The summaries contain a meaningful new result or a distinct '
                                    'productive step.'}},
 'ready_relevance.v1': {'type': 'score',
                        'instructions': 'How directly does this already-ready block advance the '
                                        'stated active milestone?',
                        'criteria': ['Unrelated',
                                     'Indirect supporting work',
                                     'Direct milestone contribution',
                                     'Directly resolves the named milestone obstacle']},
 'evidence_relevance.v1': {'type': 'score',
                           'instructions': 'How directly does the supplied evidence summary '
                                           'address the specific claim? Judge relevance only, not '
                                           'truth or acceptance.',
                           'criteria': ['Unrelated or absent',
                                        'Related topic but not the claim',
                                        'Addresses part of the claim',
                                        'Directly addresses the complete claim']},
 'review_class.v1': {'type': 'choice',
                     'instructions': 'Which label describes the supplied review findings? Do not '
                                     'authorize acceptance or infer missing checks.',
                     'criteria': {'accept': 'Findings explicitly report the scoped requirements '
                                            'satisfied with no unresolved defect.',
                                  'needs_changes': 'Findings identify a specific fixable defect '
                                                   'within the current scope.',
                                  'escalate': 'Findings are missing, conflicting or need an '
                                              'authority outside the reviewer.'}},
 'model_profile.v1': {'type': 'choice',
                      'instructions': 'Which eligible model and reasoning profile best fits the '
                                      'summarized work complexity? Choose insufficient if the '
                                      'facts do not distinguish them.',
                      'criteria': {'routine': 'Routine bounded work for an available lower-cost '
                                              'Codex worker.',
                                   'analysis': 'Bounded analytical work for an available '
                                               'host-approved reasoning profile.',
                                   'astra': 'Open-ended planning, architecture, difficult '
                                            'implementation or debugging, disagreements, final '
                                            'review, proof or acceptance.',
                                   'insufficient': 'No clear eligible profile.'}}}
