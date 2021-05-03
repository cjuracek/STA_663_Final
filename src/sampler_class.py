from collections import Counter
from random import choices

from src.utility import get_unique_words

import numpy as np
from tqdm import trange
from scipy.stats import mode


class LatentDirichletAllocation:

    def __init__(self, iden_to_tokens, K, alpha, beta):
        self.iden_to_tokens = iden_to_tokens
        self.K = K
        self.alpha = alpha
        self.beta = beta
        self.vocabulary = get_unique_words(iden_to_tokens.values())
        self.W = len(self.vocabulary)
        self.theta_matrix = np.zeros((K, len(iden_to_tokens)))
        self.phi_matrix = np.zeros((K, len(self.vocabulary)))

    def fit(self, alpha, beta, niter):
        """ Perform collapsed Gibbs sampling to discover latent topics in corpus

        :param alpha: Determines sparsity of topic distributions per document
        :param beta: Determines sparsity of word distributions per topic
        :param niter: Number of iterations to run the Gibbs sampler for
        """

        document_word_topics_MC, document_topic_counts, word_topic_counts, total_topic_counts = self._initialize_topics()

        for j in trange(niter):  # One iteration of Gibbs sampler
            print(f'Running iteration {j + 1} out of {niter}')
            for doc, words in self.iden_to_tokens.items():
                for i, word in enumerate(words):
                    densities = np.zeros(self.K)
                    curr_topic = document_word_topics_MC[doc][i][-1]  # Get most recent topic of MC chain

                    # Calculate probability that a given latent topic z_ij belongs to topic k for each k
                    for k in range(1, self.K + 1):

                        # Relevant counts needed for computation - see paragraph before Eq. 1
                        N_kj = document_topic_counts[doc][k]
                        N_wk = word_topic_counts[word][k]
                        N_k = total_topic_counts[k]

                        # New draw is conditioned on everything BUT this observation
                        if curr_topic == k:
                            N_kj -= 1
                            N_wk -= 1
                            N_k -= 1

                        # Eq. 1
                        a_kj = N_kj + alpha
                        b_wk = (N_wk + beta) / (N_k + self.W * beta)
                        densities[k - 1] = a_kj * b_wk

                    # Draw a new topic and append to MC - normalization not needed
                    new_topic = choices(range(1, self.K + 1), weights=densities)[0]
                    document_word_topics_MC[doc][i].append(new_topic)

                    # No need to update counts if topic is the same
                    if new_topic == curr_topic:
                        continue

                    # Update counts
                    document_topic_counts[doc][curr_topic] -= 1
                    document_topic_counts[doc][new_topic] += 1

                    word_topic_counts[word][curr_topic] -= 1
                    word_topic_counts[word][new_topic] += 1

                    total_topic_counts[curr_topic] -= 1
                    total_topic_counts[new_topic] += 1

        # Determine topic for word from the chain
        document_word_topics = self._compute_MC_topic_approx(document_word_topics_MC)

        # Estimate other model parameters we are interested in
        phi_matrix = _compute_phi_estimates(word_topic_counts, total_topic_counts, beta)
        theta_matrix = compute_theta_estimates(document_topic_counts, K, alpha)

        return document_word_topics, phi_matrix, theta_matrix

    def _compute_phi_estimates(self, word_topic_counts, total_topic_counts):
        """
        Compute estimate of the phi matrix, containing word distributions per topic

        :param word_topic_counts: Dictionary that maps words to their respective counts per topic
        :param total_topic_counts: Dictionary that maps each topic to the number of times it appears in corpus
        """

        for w, word in enumerate(self.vocabulary):
            for k in range(1, self.K + 1):
                N_wk = word_topic_counts[word][k]
                N_k = total_topic_counts[k]

                self.phi_matrix[k - 1, w] = (N_wk + self.beta) / (N_k + self.W * self.beta)

    def _initialize_topics(self):
        """
        Randomly initialize topic / word count information needed for sampling

        :return: 4 dictionaries of counts (see comments below)
        """

        # Contains the ordered list of topics for each document (Dict of lists)
        document_word_topics_MC = {}

        # Counts of each topic per document (Dict of dicts)
        document_topic_counts = {title: Counter() for title in self.iden_to_tokens.keys()}

        # Counts number of times a given word is assigned to each topic (dict of dicts)
        word_topic_counts = {word: Counter() for word in self.vocabulary}

        # Counts of each topic across all documents
        total_topic_counts = Counter()

        for doc, words in self.iden_to_tokens.items():

            # Start with randomly assigned topics - update appropriate counts
            topics = np.random.randint(low=1, high=self.K + 1, size=len(words))
            document_word_topics_MC[doc] = [[topic] for topic in topics]
            document_topic_counts[doc].update(topics)
            total_topic_counts.update(topics)

            # Update the topic counts per word
            for unique_word in set(words):
                unique_word_topics = [topic for idx, topic in enumerate(topics) if words[idx] == unique_word]
                word_topic_counts[unique_word].update(unique_word_topics)

        return document_word_topics_MC, document_topic_counts, word_topic_counts, total_topic_counts

    def _compute_MC_topic_approx(self, document_word_topics_MC):
        """
        Given a Markov chain of word topics, compute a Monte Carlo approximation by picking mode of topics

        :param document_word_topics: Dictionary that maps identifiers (titles) to a Markov chain of their topics
        :return: Dictionary that maps identifiers (titles) to the Monte Carlo approx of their topics (mode)
        """

        document_word_topics = {title: [] for title in document_word_topics_MC.keys()}
        for doc, words in document_word_topics_MC.items():
            for i, word in enumerate(words):
                most_frequent_topic = mode(document_word_topics_MC[doc][i], axis=None)[0][0]
                document_word_topics[doc].append(most_frequent_topic)

        return document_word_topics

    def get_top_n_words(self, n, return_probs=False):
        topic_top_words = {}

        for k in range(self.phi_matrix.shape[0]):
            # Find the top probability indices, then take the first n of them
            top_n_idx = np.argsort(self.phi_matrix[k, :])[::-1][:n]
            top_n_words = [self.vocabulary[i] for i in top_n_idx]

            if return_probs:
                top_n_probs = self.phi_matrix[k, top_n_idx]
                top_n_probs = np.around(top_n_probs, 4)
                topic_top_words[k + 1] = [(word, prob) for word, prob in zip(top_n_words, top_n_probs)]
            else:
                topic_top_words[k + 1] = top_n_words

        return topic_top_words