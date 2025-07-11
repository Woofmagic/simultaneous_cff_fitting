"""
Here, we define the DNN model architecture used for 
any fitting procedure.
"""

# 3rd Party Library | NumPy
import numpy as np

# 3rd Party Library | TensorFlow
import tensorflow as tf

# 3rd Party Library | bkm10:
from bkm10_lib import DifferentialCrossSection, CFFInputs, BKM10Inputs, backend, BKMFormalism

# 3rd Party Library | TensorFlow:
from tensorflow.keras.layers import Input

# 3rd Party Library | TensorFlow:
from tensorflow.keras.layers import Concatenate

# 3rd Party Library | TensorFlow:
from tensorflow.keras.layers import Dense

# 3rd Party Library | TensorFlow:
from tensorflow.keras.models import Model

# 3rd Party Library | TensorFlow:
from tensorflow.keras.utils import register_keras_serializable

from models.loss_functions import simultaneous_fit_loss

from statics.static_strings import _HYPERPARAMETER_LEARNING_RATE
from statics.static_strings import _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_1
from statics.static_strings import _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_2
from statics.static_strings import _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_3
from statics.static_strings import _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_4
from statics.static_strings import _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_5

from statics.constants import _MASS_OF_PROTON_IN_GEV, _ELECTROMAGNETIC_FINE_STRUCTURE_CONSTANT, _ELECTRIC_FORM_FACTOR_CONSTANT, _PROTON_MAGNETIC_MOMENT

SETTING_VERBOSE = True
SETTING_DEBUG = True

@register_keras_serializable()
class CrossSectionLayer(tf.keras.layers.Layer):

    def __init__(
            self,
            target_polarization = 0.0,
            lepton_beam_polarization = 0.0,
            using_ww = True,
            **kwargs):
        
        # (1): Inherit Layer class properties:
        super().__init__(**kwargs)

        # (2): Obtain the target polarization:
        self.target_polarization = target_polarization

        # (3): Obtain the beam polarization:
        self.lepton_beam_polarization = lepton_beam_polarization

        # (4): Decide if we're using the WW relations:
        self.using_ww = using_ww

    def call(self, inputs):
        """
        ## Description:
        This function is *required* in order to tell TF what to do when we register this
        as a layer of some ANN. It should contain all the logic that is needed. Our goal here 
        is to anticipate the passage of 5 + 4 different values --- in order, they are: lepton
        beam energy, photon virtuality, Bjorken x, hadronic momentum transfer, the azimuthal 
        angle phi, and the four CFFs. With these 9 inputs, we *compute* a single output that 
        we call the cross section.
        """
        

        kinematics = inputs[..., :5]

        cffs = inputs[..., 5:]

        # return tf.reduce_sum(cffs, axis=-1, keepdims=True)

        # (X): DUMMY COMPUTATION FOR NOW:
        differential_cross_section = self.compute_cross_section([kinematics, cffs])

        # (X): The calculation requires that we use TF not NumPy to do stuff:
        # backend.set_backend('tensorflow')

        # # (X): Set up the BKM10 kinematic inputs:
        # bkm_inputs = BKM10Inputs(
        #     squared_Q_momentum_transfer = q_squared,
        #     x_Bjorken = x_bjorken,
        #     squared_hadronic_momentum_transfer_t = t,
        #     lab_kinematics_k = k)

        # # (X): Set up the BKM10 CFF inputs:
        # cff_inputs = CFFInputs(
        #     compton_form_factor_h = backend.math.complex(real_H, imag_H),
        #     compton_form_factor_h_tilde = backend.math.complex(real_Ht, imag_Ht),
        #     compton_form_factor_e = backend.math.complex(real_E, imag_E),
        #     compton_form_factor_e_tilde = backend.math.complex(real_Et, imag_Et))

        # # (X): Construct the required configuration dictionary:
        # configuration = {
        #     "kinematics": bkm_inputs,
        #     "cff_inputs": cff_inputs,
        #     "target_polarization": self.target_polarization,
        #     "lepton_beam_polarization": self.lepton_beam_polarization,
        #     "using_ww": self.using_ww
        # }

        # # (X): Compute the differential cross section accordingly:
        # differential_cross_section = DifferentialCrossSection(configuration, verbose = True).compute_cross_section(phi)

        # (X): Re-cast sigma into a single value (I think):
        # return tf.expand_dims(differential_cross_section, axis = -1)
        return differential_cross_section
    
    @tf.function
    def compute_cross_section(self, inputs):
        """
        ## Description:
        This is a *panic* function that will compute ALL of the required
        coefficients that go into the cross section *and* the cross-section
        itself.
        """

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Received inputs: {inputs}")

        # (X): Unpack the inputs into the CFFs and the kinematics.
        # | The inputs will be a KerasTensor of shape (None, 5) and another
        # | KerasTensor of shape (None, 8). That is, the five kinematic
        # | quantities and the eight numbers for the CFFs.
        kinematics, cffs = inputs

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Obtained kinematics from inputs: {kinematics}")

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Obtained CFFs from inputs: {cffs}")

        # (X): Extract the eight CFFs from the DNN:
        real_H, imag_H, real_E, imag_E, real_Ht, imag_Ht, real_Et, imag_Et = tf.unstack(cffs, axis = -1)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Unstacked CFFs\n> {real_H, imag_H, real_E, imag_E, real_Ht, imag_Ht, real_Et, imag_Et}")

        # (X): Extract the kinematics from the DNN:
        q_squared, x_bjorken, t, k, phi = tf.unstack(kinematics, axis = -1)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Unstacked kinematics\n> {q_squared, x_bjorken, t, k, phi}")

        # (X): Compute epsilon:
        epsilon = self.calculate_kinematics_epsilon(q_squared, x_bjorken)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed epsilon: {epsilon}")

        # (X): Compute "y":
        y = self.calculate_kinematics_lepton_energy_fraction_y(q_squared, k, epsilon)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed lepton_energy_fraction: {y}")

        # (X): Comute skewness "xi":
        xi = self.calculate_kinematics_skewness_parameter(q_squared, x_bjorken, t)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed skewness: {xi}")

        # (X): Calculate t_minimum
        t_min = self.calculate_kinematics_t_min(q_squared, x_bjorken, epsilon)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed t mimumum: {t_min}")

        # (X): Calculate t':
        t_prime = self.calculate_kinematics_t_prime(t, t_min)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed t prime: {t_prime}")

        # (X): Calculate Ktilde:
        k_tilde = self.calculate_kinematics_k_tilde(q_squared, x_bjorken, y, t, epsilon, t_min)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed K tilde: {k_tilde}")

        # (X): Calculate K:
        capital_k = self.calculate_kinematics_k(q_squared, y, epsilon, k_tilde)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed K: {capital_k}")

        # (X): Calculate k.delta:
        k_dot_delta = self.calculate_k_dot_delta(q_squared, x_bjorken, t, phi, epsilon, y, k)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed K.delta: {k_dot_delta}")

        # (X): Calculate P_{1}:
        p1 = self.calculate_lepton_propagator_p1(q_squared, k_dot_delta)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed propagator p1: {p1}")

        # (X): Calculate P_{2}:
        p2 = self.calculate_lepton_propagator_p2(q_squared, t, k_dot_delta)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed propagator p1: {p2}")

        # (X): Calculate the Electric Form Factor
        fe = self.calculate_form_factor_electric(t)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed F_E: {fe}")

        # (12): Calculate the Magnetic Form Factor
        fg = self.calculate_form_factor_magnetic(fe)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed F_G: {fg}")

        # (13): Calculate the Pauli Form Factor, F2:
        f2 = self.calculate_form_factor_pauli_f2(t, fe, fg)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed F_2: {f2}")

        # (14): Calculate the Dirac Form Factor, F1:
        f1 = self.calculate_form_factor_dirac_f1(fg, f2)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed F_1: {f1}")

        # (X): Calculate prefactor:
        prefactor = self.calculate_bkm10_cross_section_prefactor(q_squared, x_bjorken, epsilon, y)
        
        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed BKM10 cross-section prefactor: {prefactor}")

        # (X): Calculate the Curly C:
        curly_c_i_real, curly_c_i_imag = self.calculate_curly_C_unpolarized_interference(
            q_squared, x_bjorken, t, f1, f2, real_H, imag_H, real_Ht, imag_Ht, real_E, imag_E)
        
        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed real part of Curly C^I: {curly_c_i_real}")
            print(f"> [DEBUG]: Computed imaginary part of Curly C^I: {curly_c_i_imag}")
        
        # (X): Calculate the Curly C,V:
        curly_c_i_v_real, curly_c_i_v_imag = self.calculate_curly_C_unpolarized_interference_V(
            q_squared, x_bjorken, t, f1, f2, real_H, imag_H, real_E, imag_E)
        
        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed real part of Curly C^I,V: {curly_c_i_v_real}")
            print(f"> [DEBUG]: Computed imaginary part of Curly C^I,V: {curly_c_i_v_imag}")
        
        # (X): Calculate the Curly C,A:
        curly_c_i_a_real, curly_c_i_a_imag = self.calculate_curly_C_unpolarized_interference_A(
            q_squared, x_bjorken, t, f1, f2, real_Ht, imag_Ht)

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed real part of Curly C^I,A: {curly_c_i_a_real}")
            print(f"> [DEBUG]: Computed imaginary part of Curly C^I,A: {curly_c_i_a_imag}")
        
        # (X): Calculate the common factor:
        common_factor = (tf.sqrt(tf.constant(2.0, dtype = tf.float32) / q_squared) * k_tilde / (tf.constant(2.0, dtype = tf.float32) - x_bjorken))

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed modulating factor on all Curly C^I with effective CFFs: {common_factor}")
        
        # (X): Calculate the Curly C with effective form factors:
        curly_c_i_real_eff, curly_c_i_imag_eff = self.calculate_curly_C_unpolarized_interference(
            q_squared, x_bjorken, t, f1, f2, 
            self.compute_cff_effective(xi, real_H, self.using_ww),
            self.compute_cff_effective(xi, imag_H, self.using_ww),
            self.compute_cff_effective(xi, real_Ht, self.using_ww),
            self.compute_cff_effective(xi, imag_Ht, self.using_ww),
            self.compute_cff_effective(xi, real_E, self.using_ww),
            self.compute_cff_effective(xi, imag_E, self.using_ww))
        
        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed first part of real part of Curly C^I with Feff: {curly_c_i_real_eff}")
            print(f"> [DEBUG]: Computed first part of imaginary part of Curly C^I with Feff: {curly_c_i_imag_eff}")
        
        # (X): Multiply the common factor with the Curly C^I thanks to TensorFlow...
        curly_c_i_real_eff = common_factor * curly_c_i_real_eff 
        curly_c_i_imag_eff = common_factor * curly_c_i_imag_eff

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Finally computed real part of Curly C^I with Feff: {curly_c_i_real_eff}")
            print(f"> [DEBUG]: Finally computed imaginary part of Curly C^I with Feff: {curly_c_i_imag_eff}")
        
        # (X): Calculate the Curly C,V with effective form factors:
        curly_c_i_v_real_eff, curly_c_i_v_imag_eff = self.calculate_curly_C_unpolarized_interference_V(
            q_squared, x_bjorken, t, f1, f2,
            self.compute_cff_effective(xi, real_H, self.using_ww),
            self.compute_cff_effective(xi, imag_H, self.using_ww),
            self.compute_cff_effective(xi, real_E, self.using_ww),
            self.compute_cff_effective(xi, imag_E, self.using_ww))
        
        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed first part of real part of Curly C^I,V with Feff: {curly_c_i_v_real_eff}")
            print(f"> [DEBUG]: Computed first part of imaginary part of Curly C^I,V with Feff: {curly_c_i_v_imag_eff}")
        
        # (X): Multiply the common factor with the Curly C^I,V thanks to TensorFlow...
        curly_c_i_v_real_eff = common_factor * curly_c_i_v_real_eff 
        curly_c_i_v_imag_eff = common_factor * curly_c_i_v_imag_eff

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Finally computed real part of Curly C^I,V with Feff: {curly_c_i_v_real_eff}")
            print(f"> [DEBUG]: Finally computed imaginary part of Curly C^I,V with Feff: {curly_c_i_v_imag_eff}")
        
        # (X): Calculate the Curly C,A with effective form factors:
        curly_c_i_a_real_eff, curly_c_i_a_imag_eff = self.calculate_curly_C_unpolarized_interference_A(
            q_squared, x_bjorken, t, f1, f2,
            self.compute_cff_effective(xi, real_Ht, self.using_ww),
            self.compute_cff_effective(xi, imag_Ht, self.using_ww))
        
        if SETTING_DEBUG:
            print(f"> [DEBUG]: Computed first part of real part of Curly C^I,V with Feff: {curly_c_i_a_real_eff}")
            print(f"> [DEBUG]: Computed first part of imaginary part of Curly C^I,V with Feff: {curly_c_i_a_imag_eff}")

        # (X): Multiply the common factor with the Curly C^I,A thanks to TensorFlow...
        curly_c_i_real_eff = common_factor * curly_c_i_real_eff 
        curly_c_i_a_real_eff = common_factor * curly_c_i_a_real_eff

        if SETTING_DEBUG:
            print(f"> [DEBUG]: Finally computed real part of Curly C^I,A with Feff: {curly_c_i_real_eff}")
            print(f"> [DEBUG]: Finally computed imaginary part of Curly C^I,A with Feff: {curly_c_i_a_real_eff}")

        # (X): Compute the three n = 0 unpolarized coefficients with TF:
        c0pp_tf = self.calculate_c_0_plus_plus_unpolarized(q_squared, x_bjorken, t, epsilon, y, k_tilde)
        c0ppv_tf = self.calculate_c_0_plus_plus_unpolarized_V(q_squared, x_bjorken, t, epsilon, y, k_tilde)
        c0ppa_tf = self.calculate_c_0_plus_plus_unpolarized_A(q_squared, x_bjorken, t, epsilon, y, k_tilde)

        # (X): Compute the three n = 1 unpolaried coefficients with TF:
        c1pp_tf = self.calculate_c_1_plus_plus_unpolarized(q_squared, x_bjorken, t, epsilon, y, capital_k)
        c1ppv_tf = self.calculate_c_1_plus_plus_unpolarized_V(q_squared, x_bjorken, t, epsilon, y, t_prime, capital_k)
        c1ppa_tf = self.calculate_c_1_plus_plus_unpolarized_A(q_squared, x_bjorken, t, epsilon, y, t_prime, capital_k)

        # (X): Compute the three n = 2 unpolaried coefficients with TF:
        c2pp_tf = self.calculate_c_2_plus_plus_unpolarized(q_squared, x_bjorken, t, epsilon, y, t_prime, k_tilde)
        c2ppv_tf = self.calculate_c_2_plus_plus_unpolarized_V(q_squared, x_bjorken, t, epsilon, y, t_prime, k_tilde)
        c2ppa_tf = self.calculate_c_2_plus_plus_unpolarized_A(q_squared, x_bjorken, t, epsilon, y, t_prime, k_tilde)

        # (X): Compute the three n = 3 unpolaried coefficients with TF:
        c3pp_tf = self.calculate_c_3_plus_plus_unpolarized(q_squared, x_bjorken, t, epsilon, y, capital_k)
        c3ppv_tf = self.calculate_c_3_plus_plus_unpolarized_V(q_squared, x_bjorken, t, epsilon, y, capital_k)
        c3ppa_tf = self.calculate_c_3_plus_plus_unpolarized_A(q_squared, x_bjorken, t, epsilon, y, t_prime, capital_k)

        # (X): Compute the three n = 0 unpolarized coefficients with TF:
        c00p_tf = self.calculate_c_0_zero_plus_unpolarized(q_squared, x_bjorken, t, epsilon, y, capital_k)
        c00pv_tf = self.calculate_c_0_zero_plus_unpolarized_V(q_squared, x_bjorken, t, epsilon, y, capital_k)
        c00pa_tf = self.calculate_c_0_zero_plus_unpolarized_A(q_squared, x_bjorken, t, epsilon, y, capital_k)

        # (X): Compute the three n = 1 unpolaried coefficients with TF:
        c10p_tf = self.calculate_c_1_zero_plus_unpolarized(q_squared, x_bjorken, t, epsilon, y, t_prime)
        c10pv_tf  = self.calculate_c_1_zero_plus_unpolarized_V(q_squared, x_bjorken, t, epsilon, y, k_tilde)
        c10pa_tf  = self.calculate_c_1_zero_plus_unpolarized_A(q_squared, x_bjorken, t, epsilon, y, k_tilde)

        # (X): Compute the three n = 2 unpolaried coefficients with TF:
        c20p_tf = self.calculate_c_2_zero_plus_unpolarized(q_squared, x_bjorken, t, epsilon, y, capital_k)
        c20pv_tf = self.calculate_c_2_zero_plus_unpolarized_V(q_squared, x_bjorken, t, epsilon, y, capital_k)
        c20pa_tf = self.calculate_c_2_zero_plus_unpolarized_A(q_squared, x_bjorken, t, epsilon, y, t_prime, capital_k)

        # (X): Compute the three n = 3 unpolaried coefficients with TF:
        c30p_tf = tf.zeros_like(c0pp_tf)
        c30pv_tf = tf.zeros_like(c0pp_tf)
        c30pa_tf = tf.zeros_like(c0pp_tf)

        # (X): Sum together all the BH contributions:
        bh_contribution = tf.zeros_like(c0pp_tf)

        # (X): Sum together all the DVCS contributions:
        dvcs_contribution = tf.zeros_like(c0pp_tf)

        # (X): Obtain the prefactor for the interference contribution:
        interference_prefactor = tf.constant(1.0, dtype = tf.float32) / (x_bjorken * y**3 * t * p1 * p2)

        # (X): Obtain the c__{0} coefficient:
        c_0 = (
            c0pp_tf * curly_c_i_real + c0ppv_tf * curly_c_i_v_real + c0ppa_tf * curly_c_i_a_real +
            c00p_tf * curly_c_i_real_eff + c00pv_tf * curly_c_i_v_real_eff + c00pa_tf * curly_c_i_a_real_eff)
        
        # (X): Obtain the c__{1} coefficient:
        c_1 = (
            c1pp_tf * curly_c_i_real + c1ppv_tf * curly_c_i_v_real + c1ppa_tf * curly_c_i_a_real +
            c10p_tf * curly_c_i_real_eff + c10pv_tf * curly_c_i_v_real_eff + c10pa_tf * curly_c_i_a_real_eff)
        
        # (X): Obtain the c__{2} coefficient:
        c_2 = (
            c2pp_tf * curly_c_i_real + c2ppv_tf * curly_c_i_v_real + c2ppa_tf * curly_c_i_a_real +
            c20p_tf * curly_c_i_real_eff + c20pv_tf * curly_c_i_v_real_eff + c20pa_tf * curly_c_i_a_real_eff)
        
        # (X): Obtain the c__{3} coefficient:
        c_3 = (
            c3pp_tf * curly_c_i_real + c3ppv_tf * curly_c_i_v_real + c3ppa_tf * curly_c_i_a_real +
            c30p_tf * curly_c_i_real_eff + c30pv_tf * curly_c_i_v_real_eff + c30pa_tf * curly_c_i_a_real_eff)

        # (X): Sum together all the Interference contributions:
        interference_contribution = (interference_prefactor * (
            c_0 * tf.cos(tf.constant(0.0, dtype = tf.float32) * tf.constant(np.pi, dtype = tf.float32) - self.convert_degrees_to_radians(phi)) +
            c_1 * tf.cos(tf.constant(1.0, dtype = tf.float32) * tf.constant(np.pi, dtype = tf.float32) - self.convert_degrees_to_radians(phi)) +
            c_2 * tf.cos(tf.constant(2.0, dtype = tf.float32) * tf.constant(np.pi, dtype = tf.float32) - self.convert_degrees_to_radians(phi)) +
            c_3 * tf.cos(tf.constant(3.0, dtype = tf.float32) * tf.constant(np.pi, dtype = tf.float32) - self.convert_degrees_to_radians(phi))
        ))

        # (X): Compute the cross-section:
        cross_section = (prefactor * (
            bh_contribution + dvcs_contribution + interference_contribution
        ))

        # (X): A first pass of computing the cross section:
        # cross_section = real_H**2 + imag_H**2 + tf.constant(0.5, dtype = tf.float32) * tf.cos(phi) * real_E + 0.1 * q_ssquared

        # (X): A second pass of computing the cross section:
        # | This is important: If you do not use *all* of the inputs given to the network, then
        # | TensorFlow will complain that there is nothing to compute gradients with respect to.
        # | This second pass revealed this. The earlier version of it did NOT include any CFFs,
        # | and TensorFlow complained that there were no gradients. All we had to do was multiply by a 
        # | single CFF, and everything worked.
        # cross_section = (prefactor * c0pp_tf * tf.cos(0. * phi)) * real_H**2 + imag_H**2 + tf.constant(0.5, dtype = tf.fdloat32) * tf.cos(phi) * real_E + 0.1 * q_squared

        return cross_section
    
    @tf.function
    def convert_degrees_to_radians(self, degrees):
        return (degrees * tf.constant(np.pi, dtype = tf.float32) / 180.)
    
    @tf.function
    def calculate_kinematics_epsilon(
        self,
        squared_Q_momentum_transfer: float,
        x_Bjorken: float, 
        verbose: bool = False) -> float:
        try:

            # (1): Calculate Epsilon right away:
            epsilon = (tf.constant(2.0, dtype = tf.float32) * x_Bjorken * _MASS_OF_PROTON_IN_GEV) / tf.sqrt(squared_Q_momentum_transfer)

            # (tf.constant(1.0, dtype = tf.float32)1): If verbose, print the result:
            if verbose:
                tf.print(f"> Calculated epsilon to be:\n{epsilon}")

            # (2): Return Epsilon:
            return epsilon
        
        except Exception as ERROR:
            tf.print(f"> Error in computing kinematic epsilon:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
    
    @tf.function
    def calculate_kinematics_lepton_energy_fraction_y(
        self,
        squared_Q_momentum_transfer: float, 
        lab_kinematics_k: float,
        epsilon: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the y right away:
            lepton_energy_fraction_y = tf.sqrt(squared_Q_momentum_transfer) / (epsilon * lab_kinematics_k)

            # (tf.constant(1.0, dtype = tf.float32)1): If verbose output, then print the result:
            if verbose:
                tf.print(f"> Calculated y to be:\n{lepton_energy_fraction_y}")

            # (2): Return the calculation:
            return lepton_energy_fraction_y
        
        except Exception as ERROR:
            tf.print(f"> Error in computing lepton_energy_fraction_y:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_kinematics_skewness_parameter(
        self,
        squared_Q_momentum_transfer: float,
        x_Bjorken: float,
        squared_hadronic_momentum_transfer_t: float,
        verbose: bool = False) -> float:
        try:

            # (1): The Numerator:
            numerator = (tf.constant(1.0, dtype = tf.float32) + (squared_hadronic_momentum_transfer_t / (tf.constant(2.0, dtype = tf.float32) * squared_Q_momentum_transfer)))

            # (2): The Denominator:
            denominator = (tf.constant(2.0, dtype = tf.float32) - x_Bjorken + (x_Bjorken * squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer))

            # (3): Calculate the Skewness Parameter:
            skewness_parameter = x_Bjorken * numerator / denominator

            # (3.1): If verbose, print the output:
            if verbose:
                tf.print(f"> Calculated skewness xi to be:\n{skewness_parameter}")

            # (4): Return Xi:
            return skewness_parameter
        
        except Exception as ERROR:
            tf.print(f"> Error in computing skewness xi:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
    
    @tf.function
    def calculate_kinematics_t_min(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        epsilon: float, 
        verbose: bool = False) -> float:
        try:

            # (1): Calculate 1 - x_{B}:
            one_minus_xb = tf.constant(1.0, dtype = tf.float32) - x_Bjorken

            # (2): Calculate the numerator:
            numerator = (tf.constant(2.0, dtype = tf.float32) * one_minus_xb * (tf.constant(1.0, dtype = tf.float32) - tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2))) + epsilon**2

            # (3): Calculate the denominator:
            denominator = (tf.constant(4.0, dtype = tf.float32) * x_Bjorken * one_minus_xb) + epsilon**2

            # (4): Obtain the t minimum
            t_minimum = -tf.constant(1.0, dtype = tf.float32) * squared_Q_momentum_transfer * numerator / denominator

            # (tf.constant(4.0, dtype = tf.float32)1): If verbose, print the result:
            if verbose:
                tf.print(f"> Calculated t_minimum to be:\n{t_minimum}")

            # (5): Print the result:
            return t_minimum

        except Exception as ERROR:
            tf.print(f"> Error calculating t_minimum: \n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_kinematics_t_prime(
        self,
        squared_hadronic_momentum_transfer_t: float,
        squared_hadronic_momentum_transfer_t_minimum: float,
        verbose: bool = False) -> float:
        try:

            # (1): Obtain the t_prime immediately
            t_prime = squared_hadronic_momentum_transfer_t - squared_hadronic_momentum_transfer_t_minimum

            # (tf.constant(1.0, dtype = tf.float32)1): If verbose, print the result:
            if verbose:
                tf.print(f"> Calculated t prime to be:\n{t_prime}")

            # (2): Return t_prime
            return t_prime

        except Exception as ERROR:
            tf.print(f"> Error calculating t_prime:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_kinematics_k_tilde(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float,
        lepton_energy_fraction_y: float,
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float, 
        squared_hadronic_momentum_transfer_t_minimum: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate recurring quantity t_{min} - t
            tmin_minus_t = squared_hadronic_momentum_transfer_t_minimum - squared_hadronic_momentum_transfer_t

            # (2): Calculate the duplicate quantity 1 - x_{B}
            one_minus_xb = tf.constant(1.0, dtype = tf.float32) - x_Bjorken

            # (3): Calculate the crazy root quantity:
            second_root_quantity = (one_minus_xb * tf.sqrt((tf.constant(1.0, dtype = tf.float32) + epsilon**2))) + ((tmin_minus_t * (epsilon**2 + (tf.constant(4.0, dtype = tf.float32) * one_minus_xb * x_Bjorken))) / (tf.constant(4.0, dtype = tf.float32) * squared_Q_momentum_transfer))

            # (4): Calculate the first annoying root quantity:
            first_root_quantity = tf.sqrt(tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - lepton_energy_fraction_y**2 * epsilon**2 / tf.constant(4.0, dtype = tf.float32))
            
            # (5): Calculate K_tilde
            k_tilde = tf.sqrt(tmin_minus_t) * tf.sqrt(second_root_quantity)

            # (6): Print the result of the calculation:
            if verbose:
                tf.print(f"> Calculated k_tilde to be:\n{k_tilde}")

            # (7) Return:
            return k_tilde

        except Exception as ERROR:
            tf.print(f"> Error in calculating K_tilde:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_kinematics_k(
        self,
        squared_Q_momentum_transfer: float, 
        lepton_energy_fraction_y: float,
        epsilon: float,
        k_tilde: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the amazing prefactor:
            prefactor = tf.sqrt(((tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y + (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))) / squared_Q_momentum_transfer))

            # (2): Calculate the remaining part of the term:
            kinematic_k = prefactor * k_tilde

            # (tf.constant(2.0, dtype = tf.float32)1); If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated kinematic K to be:\n{kinematic_k}")

            # (3): Return the value:
            return kinematic_k

        except Exception as ERROR:
            tf.print(f"> Error in calculating derived kinematic K:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_k_dot_delta(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        azimuthal_phi: float,
        epsilon: float, 
        lepton_energy_fraction_y: float,
        kinematic_k: float,
        verbose: bool = False):
        try:
        
            # (1): The prefactor: \frac{Q^{2}}{2 y (1 + \varepsilon^{2})}
            prefactor = squared_Q_momentum_transfer / (tf.constant(2.0, dtype = tf.float32) * lepton_energy_fraction_y * (tf.constant(1.0, dtype = tf.float32) + epsilon**2))

            # (2): Second term in parentheses: Phi-Dependent Term: 2 K tf.cos(\phi)
            phi_dependence = tf.constant(2.0, dtype = tf.float32) * kinematic_k * tf.cos(tf.constant(np.pi, dtype = tf.float32) - self.convert_degrees_to_radians(azimuthal_phi))
            
            # (3): Prefactor of third term in parentheses: \frac{t}{Q^{2}}
            ratio_delta_to_q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (4): Second term in the third term's parentheses: x_{B} (2 - y)
            bjorken_scaling = x_Bjorken * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y)

            # (5): Third term in the third term's parentheses: \frac{y \varepsilon^{2}}{2}
            ratio_y_epsilon = lepton_energy_fraction_y * epsilon**2 / tf.constant(2.0, dtype = tf.float32)

            # (6): Adding up all the "correction" pieces to the prefactor, written as (1 + correction)
            correction = phi_dependence - (ratio_delta_to_q_squared * (tf.constant(1.0, dtype = tf.float32) - bjorken_scaling + ratio_y_epsilon)) + (ratio_y_epsilon)

            # (7): Writing it explicitly as "1 + correction"
            in_parentheses = tf.constant(1.0, dtype = tf.float32) + correction

            # (8): The actual equation:
            k_dot_delta_result = -tf.constant(1.0, dtype = tf.float32) * prefactor * in_parentheses

            # (tf.constant(8.0, dtype = tf.float32)1): If verbose, print the output:
            if verbose:
                tf.print(f"> Calculated k dot delta: {k_dot_delta_result}")

            # (9): Return the number:
            return k_dot_delta_result
        
        except Exception as E:
            tf.print(f"> Error in calculating k.Delta:\n> {E}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_lepton_propagator_p1(
        self,
        squared_Q_momentum_transfer: float, 
        k_dot_delta: float,
        verbose:bool = False) -> float:
        try:
            p1_propagator = tf.constant(1.0, dtype = tf.float32) + (tf.constant(2.0, dtype = tf.float32) * (k_dot_delta / squared_Q_momentum_transfer))
            
            if verbose:
                tf.print(f"> Computed the P1 propagator to be:\n{p1_propagator}")

            return p1_propagator
        
        except Exception as E:
            tf.print(f"> Error in computing p1 propagator:\n> {E}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_lepton_propagator_p2(
        self,
        squared_Q_momentum_transfer: float, 
        squared_hadronic_momentum_transfer_t: float,
        k_dot_delta: float,
        verbose: bool = False) -> float:
        try:
            p2_propagator = (-tf.constant(2.0, dtype = tf.float32) * (k_dot_delta / squared_Q_momentum_transfer)) + (squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer)
            
            if verbose:
                tf.print(f"> Computed the P2 propagator to be:\n{p2_propagator}")

            return p2_propagator
        
        except Exception as E:
            tf.print(f"> Error in computing p2 propagator:\n> {E}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_form_factor_electric(
        self,
        squared_hadronic_momentum_transfer_t: float,
        verbose: bool = False) -> float:
        try:
            
            # (1): Calculate the mysterious denominator:
            denominator = tf.constant(1.0, dtype = tf.float32) - (squared_hadronic_momentum_transfer_t / _ELECTRIC_FORM_FACTOR_CONSTANT)

            # (2): Calculate the F_{E}:
            form_factor_electric = tf.constant(1.0, dtype = tf.float32) / (denominator**2)

            if verbose:
                tf.print(f"> Calculated electric form factor as: {form_factor_electric}")

            return form_factor_electric

        except Exception as ERROR:
            tf.print(f"> Error in calculating electric form factor:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_form_factor_magnetic(
        self,
        electric_form_factor: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the F_{M}:
            form_factor_magnetic = _PROTON_MAGNETIC_MOMENT * electric_form_factor

            if verbose:
                tf.print(f"> Calculated magnetic form factor as: {form_factor_magnetic}")

            return form_factor_magnetic

        except Exception as ERROR:
            tf.print(f"> Error in calculating magnetic form factor:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_form_factor_pauli_f2(
        self,
        squared_hadronic_momentum_transfer_t: float,
        electric_form_factor: float,
        magnetic_form_factor: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate tau:
            tau = -tf.constant(1.0, dtype = tf.float32) * squared_hadronic_momentum_transfer_t / (tf.constant(4.0, dtype = tf.float32) * _MASS_OF_PROTON_IN_GEV**2)

            # (2): Calculate the numerator:
            numerator = magnetic_form_factor - electric_form_factor

            # (3): Calculate the denominator:
            denominator = tf.constant(1.0, dtype = tf.float32) + tau
        
            # (4): Calculate the Pauli form factor:
            pauli_form_factor = numerator / denominator

            if verbose:
                tf.print(f"> Calculated Fermi form factor as: {pauli_form_factor}")

            return pauli_form_factor

        except Exception as ERROR:
            tf.print(f"> Error in calculating Fermi form factor:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_form_factor_dirac_f1(
        self,
        magnetic_form_factor: float,
        pauli_f2_form_factor: float,
        verbose: bool = False) -> float:
        try:
        
            # (1): Calculate the Dirac form factor:
            dirac_form_factor = magnetic_form_factor - pauli_f2_form_factor

            if verbose:
                tf.print(f"> Calculated Dirac form factor as: {dirac_form_factor}")

            return dirac_form_factor

        except Exception as ERROR:
            tf.print(f"> Error in calculating Dirac form factor:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def compute_cff_effective(
        self,
        skewness_parameter: float,
        compton_form_factor: complex,
        use_ww: bool = False,
        verbose: bool = False) -> complex:
        try:

            # (1): Do the calculation in one line:
            if use_ww:
                cff_effective = tf.constant(2.0, dtype = tf.float32) * compton_form_factor / (tf.constant(1.0, dtype = tf.float32) + skewness_parameter)
            else:
                cff_effective = -tf.constant(2.0, dtype = tf.float32) * skewness_parameter * compton_form_factor / (tf.constant(1.0, dtype = tf.float32) + skewness_parameter)

            # (tf.constant(1.0, dtype = tf.float32)1): If verbose, log the output:
            if verbose:
                tf.print(f"> Computed the CFF effective to be:\n{cff_effective}")

            # (2): Return the output:
            return cff_effective

        except Exception as ERROR:
            tf.print(f"> Error in calculating F_effective:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_bkm10_cross_section_prefactor(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        epsilon: float, 
        lepton_energy_fraction_y: float, 
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the numerator of the prefactor
            numerator = _ELECTROMAGNETIC_FINE_STRUCTURE_CONSTANT**3 * lepton_energy_fraction_y**2 * x_Bjorken

            # (2): Calculate the denominator of the prefactor:
            denominator = tf.constant(8.0, dtype = tf.float32) * tf.constant(np.pi, dtype = tf.float32) * squared_Q_momentum_transfer**2 * tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (3): Construct the prefactor:
            prefactor = numerator / denominator

            if verbose:
                tf.print(f"> Calculated BKM10 cross-section prefactor to be:\n{prefactor}")

            # (4): Return the prefactor:
            return prefactor

        except Exception as ERROR:
            tf.print(f"> Error calculating BKM10 cross section prefactor:\n> {ERROR}")
            return 0

    @tf.function
    def calculate_curly_C_unpolarized_interference(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float,
        squared_hadronic_momentum_transfer_t: float,
        Dirac_form_factor_F1: float,
        Pauli_form_factor_F2: float,
        real_H: tf.Tensor,
        imag_H: tf.Tensor,
        real_Ht: tf.Tensor,
        imag_Ht: tf.Tensor,
        real_E: tf.Tensor,
        imag_E: tf.Tensor,
        verbose: bool = False) -> float:

        # (1): Calculate the first two terms: weighted CFFs:
        weighted_cffs_real = (Dirac_form_factor_F1 * real_H) - (squared_hadronic_momentum_transfer_t * Pauli_form_factor_F2 * real_E / (tf.constant(4.0, dtype = tf.float32) * _MASS_OF_PROTON_IN_GEV**2))
        weighted_cffs_imag = (Dirac_form_factor_F1 * imag_H) - (squared_hadronic_momentum_transfer_t * Pauli_form_factor_F2 * imag_E / (tf.constant(4.0, dtype = tf.float32) * _MASS_OF_PROTON_IN_GEV**2))

        # (2): Calculate the next term:
        second_term_real = x_Bjorken * (Dirac_form_factor_F1 + Pauli_form_factor_F2) * real_Ht / (tf.constant(2.0, dtype = tf.float32) - x_Bjorken + (x_Bjorken * squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer))
        second_term_imag = x_Bjorken * (Dirac_form_factor_F1 + Pauli_form_factor_F2) * imag_Ht / (tf.constant(2.0, dtype = tf.float32) - x_Bjorken + (x_Bjorken * squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer))

        # (3): Add them together:
        curly_C_unpolarized_interference_real = weighted_cffs_real + second_term_real
        curly_C_unpolarized_interference_imag = weighted_cffs_imag + second_term_imag

        # (tf.constant(4.0, dtype = tf.float32)1): If verbose, print the calculation:
        if verbose:
            tf.print(f"> Calculated Curly C interference unpolarized target to be:\n{curly_C_unpolarized_interference_real. curly_C_unpolarized_interference_imag}")

        # (5): Return the output:
        return curly_C_unpolarized_interference_real, curly_C_unpolarized_interference_imag

    @tf.function
    def calculate_curly_C_unpolarized_interference_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float,
        squared_hadronic_momentum_transfer_t: float,
        Dirac_form_factor_F1: float,
        Pauli_form_factor_F2: float,
        real_H: tf.Tensor,
        imag_H: tf.Tensor,
        real_E: tf.Tensor,
        imag_E: tf.Tensor,
        verbose: bool = False) -> float:

        # (1): Calculate the first two terms: weighted CFFs:
        cff_term_real = real_H + real_E
        cff_term_imag = imag_H + imag_E

        # (2): Calculate the next term:
        second_term = x_Bjorken * (Dirac_form_factor_F1 + Pauli_form_factor_F2) / (tf.constant(2.0, dtype = tf.float32) - x_Bjorken + (x_Bjorken * squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer))

        # (3): Add them together:
        curly_C_unpolarized_interference_V_real = cff_term_real * second_term
        curly_C_unpolarized_interference_V_imag = cff_term_imag * second_term

        # (tf.constant(4.0, dtype = tf.float32)1): If verbose, print the calculation:
        if verbose:
            tf.print(f"> Calculated Curly C interference V unpolarized target to be:\n{curly_C_unpolarized_interference_V_real}")

        # (5): Return the output:
        return curly_C_unpolarized_interference_V_real, curly_C_unpolarized_interference_V_imag
        
    @tf.function
    def calculate_curly_C_unpolarized_interference_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float,
        squared_hadronic_momentum_transfer_t: float,
        Dirac_form_factor_F1: float,
        Pauli_form_factor_F2: float,
        real_Ht: tf.Tensor,
        imag_Ht: tf.Tensor,
        verbose: bool = False) -> float:

        # (1): Calculate the next term:
        xb_modulation = x_Bjorken * (Dirac_form_factor_F1 + Pauli_form_factor_F2) / (tf.constant(2.0, dtype = tf.float32) - x_Bjorken + (x_Bjorken * squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer))

        # (2): Add them together:
        curly_C_unpolarized_interference_A_real = real_Ht * xb_modulation
        curly_C_unpolarized_interference_A_imag = imag_Ht * xb_modulation

        # (3.1): If verbose, print the calculation:
        if verbose:
            tf.print(f"> Calculated Curly C interference A unpolarized target to be:\n{curly_C_unpolarized_interference_A_real}")

        # (4): Return the output:
        return curly_C_unpolarized_interference_A_real, curly_C_unpolarized_interference_A_imag
    
    @tf.function
    def calculate_c_0_plus_plus_unpolarized(self,
        squared_Q_momentum_transfer,
        x_Bjorken,
        squared_hadronic_momentum_transfer_t,
        epsilon,
        lepton_energy_fraction_y,
        k_tilde):
        """
        """

        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate 1 + sqrt(1 + epsilon^{2}):
            one_plus_root_epsilon_stuff = tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared

            # (4): Calculate 2 - x_{B}:
            two_minus_xb = tf.constant(2.0, dtype = tf.float32) - x_Bjorken

            # (5): Caluclate 2 - y:
            two_minus_y = tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y

            # (6): Calculate the first term in the brackets:
            first_term_in_brackets = k_tilde**2 * two_minus_y**2 / (squared_Q_momentum_transfer * root_one_plus_epsilon_squared)

            # (7): Calculate the first part of the second term in brackets:
            second_term_in_brackets_first_part = t_over_Q_squared * two_minus_xb * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)))
            
            # (8): Calculate the numerator of the second part of the second term in brackets:
            second_term_in_brackets_second_part_numerator = tf.constant(2.0, dtype = tf.float32) * x_Bjorken * t_over_Q_squared * (two_minus_xb + tf.constant(0.5, dtype = tf.float32) * (root_one_plus_epsilon_squared - tf.constant(1.0, dtype = tf.float32)) + tf.constant(0.5, dtype = tf.float32) * epsilon**2 / x_Bjorken) + epsilon**2
            
            # (9): Calculate the second part of the second term in brackets:
            second_term_in_brackets_second_part =  tf.constant(1.0, dtype = tf.float32) + second_term_in_brackets_second_part_numerator / (two_minus_xb * one_plus_root_epsilon_stuff)
            
            # (10): Calculate the prefactor:
            prefactor = -tf.constant(4.0, dtype = tf.float32) * two_minus_y * one_plus_root_epsilon_stuff / tf.pow(root_one_plus_epsilon_squared, 4)

            # (11): Calculate the coefficient
            c_0_plus_plus_unp = prefactor * (first_term_in_brackets + second_term_in_brackets_first_part * second_term_in_brackets_second_part)

            # (12): Return the coefficient:
            return c_0_plus_plus_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_0_plus_plus_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_c_0_plus_plus_unpolarized_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        k_tilde: float,
        verbose: bool = False) -> float:

        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate the recurrent quantity 1 + sqrt(1 + epsilon^2):
            one_plus_root_epsilon_stuff = tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared

            # (4): Compute the first term in the brackets:
            first_term_in_brackets = (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y)**2 * k_tilde**2 / (root_one_plus_epsilon_squared * squared_Q_momentum_transfer)

            # (5): First multiplicative term in the second term in the brackets:
            second_term_first_multiplicative_term = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))

            # (6): Second multiplicative term in the second term in the brackets:
            second_term_second_multiplicative_term = one_plus_root_epsilon_stuff / tf.constant(2.0, dtype = tf.float32)

            # (7): Third multiplicative term in the second term in the brackets:
            second_term_third_multiplicative_term = tf.constant(1.0, dtype = tf.float32) + t_over_Q_squared

            # (8): Fourth multiplicative term numerator in the second term in the brackets:
            second_term_fourth_multiplicative_term = tf.constant(1.0, dtype = tf.float32) + (root_one_plus_epsilon_squared - tf.constant(1.0, dtype = tf.float32) + (tf.constant(2.0, dtype = tf.float32) * x_Bjorken)) * t_over_Q_squared / one_plus_root_epsilon_stuff

            # (9): Fourth multiplicative term in its entirety:
            second_term_in_brackets = second_term_first_multiplicative_term * second_term_second_multiplicative_term * second_term_third_multiplicative_term * second_term_fourth_multiplicative_term

            # (10): The prefactor in front of the brackets:
            coefficient_prefactor = tf.constant(8.0, dtype = tf.float32) * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * x_Bjorken * t_over_Q_squared / root_one_plus_epsilon_squared**4

            # (11): The entire thing:
            c_0_plus_plus_V_unp = coefficient_prefactor * (first_term_in_brackets + second_term_in_brackets)

            # (11.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_0_plus_plus_V_unp to be:\n{c_0_plus_plus_V_unp}")

            # (12): Return the coefficient:
            return c_0_plus_plus_V_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_0_plus_plus_V_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)    

    @tf.function
    def calculate_c_0_plus_plus_unpolarized_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        k_tilde: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate the recurrent quantity 1 + sqrt(1 + epsilon^2):
            one_plus_root_epsilon_stuff = tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared

            # (4): Calculate 2 - y:
            two_minus_y = tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y

            # (5): Calculate Ktilde^{2}/squaredQ:
            ktilde_over_Q_squared = k_tilde**2 / squared_Q_momentum_transfer

            # (6): Calculate the first term in the curly brackets:
            curly_bracket_first_term = two_minus_y**2 * ktilde_over_Q_squared * (one_plus_root_epsilon_stuff - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) / (tf.constant(2.0, dtype = tf.float32) * root_one_plus_epsilon_squared)

            # (7): Calculate inner parentheses term:
            deepest_parentheses_term = (x_Bjorken * (tf.constant(2.0, dtype = tf.float32) + one_plus_root_epsilon_stuff - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) / one_plus_root_epsilon_stuff + (one_plus_root_epsilon_stuff - tf.constant(2.0, dtype = tf.float32))) * t_over_Q_squared

            # (8): Calculate the square-bracket term:
            square_bracket_term = one_plus_root_epsilon_stuff * (one_plus_root_epsilon_stuff - x_Bjorken + deepest_parentheses_term) / tf.constant(2.0, dtype = tf.float32) - (tf.constant(2.0, dtype = tf.float32) * ktilde_over_Q_squared)

            # (9): Calculate the second bracket term:
            curly_bracket_second_term = (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)) * square_bracket_term

            # (10): Calculate the prefactor: 
            coefficient_prefactor = tf.constant(8.0, dtype = tf.float32) * two_minus_y * t_over_Q_squared / root_one_plus_epsilon_squared**4

            # (11): The entire thing:
            c_0_plus_plus_A_unp = coefficient_prefactor * (curly_bracket_first_term + curly_bracket_second_term)

            # (11.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_0_plus_plus_A_unp to be:\n{c_0_plus_plus_A_unp}")

            # (12): Return the coefficient:
            return c_0_plus_plus_A_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_0_plus_plus_A_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_c_1_plus_plus_unpolarized(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate 1 + sqrt(1 + epsilon^{2}):
            one_plus_root_epsilon_stuff = tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared

            # (4): Calculate first term in first brackets
            first_bracket_first_term = (tf.constant(1.0, dtype = tf.float32) + (tf.constant(1.0, dtype = tf.float32) - x_Bjorken) * (root_one_plus_epsilon_squared - tf.constant(1.0, dtype = tf.float32)) / (tf.constant(2.0, dtype = tf.float32) * x_Bjorken) + epsilon**2 / (tf.constant(4.0, dtype = tf.float32) * x_Bjorken)) * x_Bjorken * t_over_Q_squared

            # (5): Calculate the first bracket term:
            first_bracket_term = first_bracket_first_term - 3. * epsilon**2 / tf.constant(4.0, dtype = tf.float32)

            # (6): Calculate the second bracket term:
            second_bracket_term = tf.constant(1.0, dtype = tf.float32) - (tf.constant(1.0, dtype = tf.float32) - 3. * x_Bjorken) * t_over_Q_squared + (tf.constant(1.0, dtype = tf.float32) - root_one_plus_epsilon_squared + 3. * epsilon**2) * x_Bjorken * t_over_Q_squared / (one_plus_root_epsilon_stuff - epsilon**2)

            # (7): Calculate the crazy coefficient with all the y's:
            fancy_y_coefficient = tf.constant(2.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * lepton_energy_fraction_y + lepton_energy_fraction_y**2 + epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(2.0, dtype = tf.float32)

            # (8): Calculate the entire second term:
            second_term = -tf.constant(4.0, dtype = tf.float32) * shorthand_k * fancy_y_coefficient * (one_plus_root_epsilon_stuff - epsilon**2) * second_bracket_term / root_one_plus_epsilon_squared**5

            # (9): Calculate the first term:
            first_term = -tf.constant(16.0, dtype = tf.float32) * shorthand_k * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)) * first_bracket_term / root_one_plus_epsilon_squared**5

            # (10): Calculate the coefficient
            c_1_plus_plus_unp = first_term + second_term
            
            # (11.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_1_plus_plus_unp to be:\n{c_1_plus_plus_unp}")

            # (12): Return the coefficient:
            return c_1_plus_plus_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_1_plus_plus_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_c_1_plus_plus_unpolarized_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float,
        t_prime: float,
        shorthand_k: float,
        verbose: bool = False) -> float:
        # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
        root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

        # (2): Calculate the recurrent quantity t/Q^{2}:
        t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

        # (3): Calculate the first bracket term:
        first_bracket_term = (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y)**2 * (tf.constant(1.0, dtype = tf.float32) - (tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * t_over_Q_squared)

        # (4): Compute the first part of the second term in brackets:
        second_bracket_term_first_part = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)

        # (5): Compute the second part of the second term in brackets:
        second_bracket_term_second_part = tf.constant(0.5, dtype = tf.float32) * (tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * t_prime / squared_Q_momentum_transfer

        # (6): The prefactor in front of the brackets:
        coefficient_prefactor = tf.constant(16.0, dtype = tf.float32) * shorthand_k * x_Bjorken * t_over_Q_squared / tf.pow(root_one_plus_epsilon_squared, 5)

        # (7): The entire thing:
        c_1_plus_plus_V_unp = coefficient_prefactor * (first_bracket_term + second_bracket_term_first_part * second_bracket_term_second_part)

        # (7.1): If verbose, log the output:
        if verbose:
            tf.print(f"> Calculated c_1_plus_plus_V_unp to be:\n{c_1_plus_plus_V_unp}")

        # (12): Return the coefficient:
        return c_1_plus_plus_V_unp

    @tf.function
    def calculate_c_1_plus_plus_unpolarized_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        t_prime: float,
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate t'/Q^{2}
            t_prime_over_Q_squared = t_prime / squared_Q_momentum_transfer

            # (4): Calculate 1 - x_{B}:
            one_minus_xb = tf.constant(1.0, dtype = tf.float32) - x_Bjorken

            # (5): Calculate 1 - 2 x_{B}:
            one_minus_2xb = tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken

            # (6): Calculate a fancy, annoying quantity:
            fancy_y_stuff = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)

            # (7): Calculate the second contribution to the first term in brackets:
            first_bracket_term_second_part = tf.constant(1.0, dtype = tf.float32) - one_minus_2xb * t_over_Q_squared + (tf.constant(4.0, dtype = tf.float32) * x_Bjorken * one_minus_xb + epsilon**2) * t_prime_over_Q_squared / (tf.constant(4.0, dtype = tf.float32) * root_one_plus_epsilon_squared)

            # (8): Calculate the second bracket term:
            second_bracket_term = tf.constant(1.0, dtype = tf.float32) - tf.constant(0.5, dtype = tf.float32) * x_Bjorken + tf.constant(0.25, dtype = tf.float32) * (one_minus_2xb + root_one_plus_epsilon_squared) * (tf.constant(1.0, dtype = tf.float32) - t_over_Q_squared) + (tf.constant(4.0, dtype = tf.float32) * x_Bjorken * one_minus_xb + epsilon**2) * t_prime_over_Q_squared / (tf.constant(2.0, dtype = tf.float32) * root_one_plus_epsilon_squared)

            # (9): Calculate the prefactor:
            prefactor = -tf.constant(16.0, dtype = tf.float32) * shorthand_k * t_over_Q_squared / root_one_plus_epsilon_squared**4
            
            # (10): The entire thing:
            c_1_plus_plus_A_unp = prefactor * (fancy_y_stuff * first_bracket_term_second_part - (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y)**2 * second_bracket_term)

            # (10.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_1_plus_plus_A_unp to be:\n{c_1_plus_plus_A_unp}")

            # (11): Return the coefficient:
            return c_1_plus_plus_A_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_1_plus_plus_A_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_c_2_plus_plus_unpolarized(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float,
        t_prime: float,
        k_tilde: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate the first bracket quantity:
            first_bracket_term = tf.constant(2.0, dtype = tf.float32) * epsilon**2 * k_tilde**2 / (root_one_plus_epsilon_squared * (tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared) * squared_Q_momentum_transfer)
        
            # (4): Calculate the second bracket quantity:
            second_bracket_term = x_Bjorken * t_prime * t_over_Q_squared * (tf.constant(1.0, dtype = tf.float32) - x_Bjorken - tf.constant(0.5, dtype = tf.float32) * (root_one_plus_epsilon_squared - tf.constant(1.0, dtype = tf.float32)) + tf.constant(0.5, dtype = tf.float32) * epsilon**2 / x_Bjorken) / squared_Q_momentum_transfer

            # (5): Calculate the prefactor:
            prefactor = tf.constant(8.0, dtype = tf.float32) * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)) / root_one_plus_epsilon_squared**4
            
            # (6): Calculate the coefficient
            c_2_plus_plus_unp = prefactor * (first_bracket_term + second_bracket_term)
            
            # (6.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_2_plus_plus_unp to be:\n{c_2_plus_plus_unp}")

            # (7): Return the coefficient:
            return c_2_plus_plus_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_2_plus_plus_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_2_plus_plus_unpolarized_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        t_prime: float,
        k_tilde: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate t'/Q^{2}
            t_prime_over_Q_squared = t_prime / squared_Q_momentum_transfer

            # (4): Calculate the major term:
            major_term = (tf.constant(4.0, dtype = tf.float32) * k_tilde**2 / (root_one_plus_epsilon_squared * squared_Q_momentum_transfer)) + tf.constant(0.5, dtype = tf.float32) * (tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * (tf.constant(1.0, dtype = tf.float32) + t_over_Q_squared) * t_prime_over_Q_squared

            # (5): Calculate the prefactor: 
            prefactor = tf.constant(8.0, dtype = tf.float32) * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)) * x_Bjorken * t_over_Q_squared / root_one_plus_epsilon_squared**4
            
            # (6): The entire thing:
            c_2_plus_plus_V_unp = prefactor * major_term

            # (6.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_2_plus_plus_V_unp to be:\n{c_2_plus_plus_V_unp}")

            # (7): Return the coefficient:
            return c_2_plus_plus_V_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_2_plus_plus_V_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_2_plus_plus_unpolarized_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        t_prime: float,
        k_tilde: float,
        verbose: bool = False) -> float:

        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate t'/Q^{2}
            t_prime_over_Q_squared = t_prime / squared_Q_momentum_transfer

            # (4): Calculate the first bracket term:
            first_bracket_term = tf.constant(4.0, dtype = tf.float32) * (tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * k_tilde**2 / (root_one_plus_epsilon_squared * squared_Q_momentum_transfer)

            # (5): Calculate the second bracket term:
            second_bracket_term = (3.  - root_one_plus_epsilon_squared - tf.constant(2.0, dtype = tf.float32) * x_Bjorken + epsilon**2 / x_Bjorken ) * x_Bjorken * t_prime_over_Q_squared

            # (6): Calculate the prefactor: 
            prefactor = tf.constant(4.0, dtype = tf.float32) * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)) * t_over_Q_squared / root_one_plus_epsilon_squared**4
            
            # (7): The entire thing:
            c_2_plus_plus_A_unp = prefactor * (first_bracket_term - second_bracket_term)

            # (7.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_2_plus_plus_A_unp to be:\n{c_2_plus_plus_A_unp}")

            # (8): Return the coefficient:
            return c_2_plus_plus_A_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_2_plus_plus_A_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_c_3_plus_plus_unpolarized(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float,
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate the major term:
            major_term = (tf.constant(1.0, dtype = tf.float32) - x_Bjorken) * t_over_Q_squared + tf.constant(0.5, dtype = tf.float32) * (root_one_plus_epsilon_squared - tf.constant(1.0, dtype = tf.float32)) * (tf.constant(1.0, dtype = tf.float32) + t_over_Q_squared)
        
            # (4): Calculate the "intermediate" term:
            intermediate_term = (root_one_plus_epsilon_squared - tf.constant(1.0, dtype = tf.float32)) / root_one_plus_epsilon_squared**5

            # (5): Calculate the prefactor:
            prefactor = -tf.constant(8.0, dtype = tf.float32) * shorthand_k * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))
            
            # (6): Calculate the coefficient
            c_3_plus_plus_unp = prefactor * intermediate_term * major_term
            
            # (6.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_3_plus_plus_unp to be:\n{c_3_plus_plus_unp}")

            # (7): Return the coefficient:
            return c_3_plus_plus_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_3_plus_plus_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_3_plus_plus_unpolarized_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate the major term:
            major_term = root_one_plus_epsilon_squared - tf.constant(1.0, dtype = tf.float32) + (tf.constant(1.0, dtype = tf.float32) + root_one_plus_epsilon_squared - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * t_over_Q_squared

            # (4): Calculate he prefactor:
            prefactor = -tf.constant(8.0, dtype = tf.float32) * shorthand_k * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)) * x_Bjorken * t_over_Q_squared / root_one_plus_epsilon_squared**5
            
            # (5): The entire thing:
            c_3_plus_plus_V_unp = prefactor * major_term

            # (5.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_3_plus_plus_V_unp to be:\n{c_3_plus_plus_V_unp}")

            # (7): Return the coefficient:
            return c_3_plus_plus_V_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_3_plus_plus_V_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_c_3_plus_plus_unpolarized_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        t_prime: float,
        shorthand_k: float,
        verbose: bool = False) -> float:
        """
        """

        try:

            # (1): Calculate the main term:
            main_term = squared_hadronic_momentum_transfer_t * t_prime * (x_Bjorken * (tf.constant(1.0, dtype = tf.float32) - x_Bjorken) + epsilon**2 / tf.constant(4.0, dtype = tf.float32)) / squared_Q_momentum_transfer**2

            # (2): Calculate the prefactor: 
            prefactor = tf.constant(16.0, dtype = tf.float32) * shorthand_k * (tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)) / (tf.constant(1.0, dtype = tf.float32) + epsilon**2)**tf.constant(2.0, dtype = tf.float32)
            
            # (3): The entire thing:
            c_3_plus_plus_A_unp = prefactor * main_term

            # (3.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_3_plus_plus_A_unp to be:\n{c_3_plus_plus_A_unp}")

            # (4): Return the coefficient:
            return c_3_plus_plus_A_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_2_plus_plus_A_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)

    @tf.function
    def calculate_c_0_zero_plus_unpolarized(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the bracket quantity:
            bracket_quantity = epsilon**2 + squared_hadronic_momentum_transfer_t * (tf.constant(2.0, dtype = tf.float32) - 6.* x_Bjorken - epsilon**2) / (3. * squared_Q_momentum_transfer)
            
            # (2): Calculate part of the prefactor:
            prefactor = 12. * tf.sqrt(tf.constant(2.0, dtype = tf.float32)) * shorthand_k * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * tf.sqrt(tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / 4)) / tf.pow(tf.constant(1.0, dtype = tf.float32) + epsilon**2, tf.constant(2.0, dtype = tf.float32))
            
            # (3): Calculate the coefficient:
            c_0_zero_plus_unp = prefactor * bracket_quantity
            
            # (3.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_0_zero_plus_unp to be:\n{c_0_zero_plus_unp}")

            # (4): Return the coefficient:
            return c_0_zero_plus_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_0_zero_plus_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_0_zero_plus_unpolarized_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (2): Calculate the main part of the thing:
            main_part = x_Bjorken * t_over_Q_squared * (tf.constant(1.0, dtype = tf.float32) - (tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * t_over_Q_squared)

            # (3): Calculate the prefactor:
            prefactor = 24. * tf.sqrt(tf.constant(2.0, dtype = tf.float32)) * shorthand_k * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * tf.sqrt(tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (lepton_energy_fraction_y**2 * epsilon**2 / tf.constant(4.0, dtype = tf.float32))) / (tf.constant(1.0, dtype = tf.float32) + epsilon**2)**tf.constant(2.0, dtype = tf.float32)

            # (4): Stitch together the coefficient:
            c_0_zero_plus_V_unp = prefactor * main_part

            # (tf.constant(4.0, dtype = tf.float32)1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_0_zero_plus_V_unp to be:\n{c_0_zero_plus_V_unp}")

            # (5): Return the coefficient:
            return c_0_zero_plus_V_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_0_zero_plus_V_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_0_zero_plus_unpolarized_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (2): Calculate the recurrent quantity 8 - 6x_{B} + 5 epsilon^{2}:
            fancy_xb_epsilon_term = tf.constant(8.0, dtype = tf.float32) - 6. * x_Bjorken + 5. * epsilon**2

            # (3): Compute the bracketed term:
            brackets_term = tf.constant(1.0, dtype = tf.float32) - t_over_Q_squared * (tf.constant(2.0, dtype = tf.float32) - 12. * x_Bjorken * (tf.constant(1.0, dtype = tf.float32) - x_Bjorken) - epsilon**2) / fancy_xb_epsilon_term

            # (4): Calculate the prefactor:
            prefactor = tf.constant(4.0, dtype = tf.float32) * tf.sqrt(tf.constant(2.0, dtype = tf.float32)) * shorthand_k * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * tf.sqrt(tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (lepton_energy_fraction_y**2 * epsilon**2 / tf.constant(4.0, dtype = tf.float32))) / tf.pow(tf.constant(1.0, dtype = tf.float32) + epsilon**2, tf.constant(2.0, dtype = tf.float32))

            # (5): Stitch together the coefficient:
            c_0_zero_plus_A_unp = prefactor * t_over_Q_squared * fancy_xb_epsilon_term * brackets_term

            # (5.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_0_zero_plus_A_unp to be:\n{c_0_zero_plus_A_unp}")

            # (6): Return the coefficient:
            return c_0_zero_plus_A_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_0_zero_plus_A_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_1_zero_plus_unpolarized(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        t_prime: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate t'/Q^{2}
            t_prime_over_Q_squared = t_prime / squared_Q_momentum_transfer

            # (4): Calculate 1 - x_{B}:
            one_minus_xb = tf.constant(1.0, dtype = tf.float32) - x_Bjorken

            # (5): Calculate the annoying y quantity:
            y_quantity = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))

            # (6): Calculate the first term:
            first_bracket_term = (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y)**2 * t_prime_over_Q_squared * (one_minus_xb + (one_minus_xb * x_Bjorken + (epsilon**2 / tf.constant(4.0, dtype = tf.float32))) * t_prime_over_Q_squared / root_one_plus_epsilon_squared)
            
            # (7): Calculate the second term:
            second_bracket_term = y_quantity * (tf.constant(1.0, dtype = tf.float32) - (tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * t_over_Q_squared) * (epsilon**2 - tf.constant(2.0, dtype = tf.float32) * (tf.constant(1.0, dtype = tf.float32) + (epsilon**2 / (tf.constant(2.0, dtype = tf.float32) * x_Bjorken))) * x_Bjorken * t_over_Q_squared) / root_one_plus_epsilon_squared
            
            # (8): Calculate part of the prefactor:
            prefactor = tf.constant(8.0, dtype = tf.float32) * tf.sqrt(tf.constant(2.0, dtype = tf.float32) * y_quantity) / root_one_plus_epsilon_squared**4
            
            # (9): Calculate the coefficient:
            c_1_zero_plus_unp = prefactor * (first_bracket_term + second_bracket_term)
            
            # (9.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_1_zero_plus_unp to be:\n{c_1_zero_plus_unp}")

            # (9): Return the coefficient:
            return c_1_zero_plus_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_1_zero_plus_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_1_zero_plus_unpolarized_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        k_tilde: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (2): Calculate the huge y quantity:
            y_quantity = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))

            # (3): Calculate the major part:
            major_part = (2 - lepton_energy_fraction_y)**2 * k_tilde**2 / squared_Q_momentum_transfer + (tf.constant(1.0, dtype = tf.float32) - (tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * t_over_Q_squared)**2 * y_quantity

            # (4): Calculate the prefactor:
            prefactor = tf.constant(16.0, dtype = tf.float32) * tf.sqrt(tf.constant(2.0, dtype = tf.float32) * y_quantity) * x_Bjorken * t_over_Q_squared / (tf.constant(1.0, dtype = tf.float32) + epsilon**2)**tf.constant(2.0, dtype = tf.float32)

            # (5): Stitch together the coefficient:
            c_1_zero_plus_V_unp = prefactor * major_part

            # (5.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_1_zero_plus_V_unp to be:\n{c_1_zero_plus_V_unp}")

            # (6): Return the coefficient:
            return c_1_zero_plus_V_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_1_zero_plus_V_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_1_zero_plus_unpolarized_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        k_tilde: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate 1 - 2x_{B}:
            one_minus_2xb = tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken

            # (4): Calculate the annoying y quantity:
            y_quantity = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))

            # (5): Calculate the first part of the second term:
            second_term_first_part = (tf.constant(1.0, dtype = tf.float32) - one_minus_2xb * t_over_Q_squared) * y_quantity

            # (6); Calculate the second part of the second term:
            second_term_second_part = tf.constant(4.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken + 3. * epsilon**2 + t_over_Q_squared * (tf.constant(4.0, dtype = tf.float32) * x_Bjorken * (tf.constant(1.0, dtype = tf.float32) - x_Bjorken) + epsilon**2)
            
            # (7): Calculate the first term:
            first_term = k_tilde**2 * one_minus_2xb * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y)**2 / squared_Q_momentum_transfer
            
            # (8): Calculate part of the prefactor:
            prefactor = tf.constant(8.0, dtype = tf.float32) * tf.sqrt(tf.constant(2.0, dtype = tf.float32) * y_quantity) * t_over_Q_squared / root_one_plus_epsilon_squared**5
            
            # (9): Calculate the coefficient:
            c_1_zero_plus_unp_A = prefactor * (first_term + second_term_first_part * second_term_second_part)
            
            # (9.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_1_zero_plus_unp_A to be:\n{c_1_zero_plus_unp_A}")

            # (10): Return the coefficient:
            return c_1_zero_plus_unp_A

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_1_zero_plus_unp_A for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_2_zero_plus_unpolarized(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity epsilon^2/2:
            epsilon_squared_over_2 = epsilon**2 / tf.constant(2.0, dtype = tf.float32)

            # (3): Calculate the annoying y quantity:
            y_quantity = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))

            # (4): Calculate the bracket term:
            bracket_term = tf.constant(1.0, dtype = tf.float32) + ((tf.constant(1.0, dtype = tf.float32) + epsilon_squared_over_2 / x_Bjorken) / (tf.constant(1.0, dtype = tf.float32) + epsilon_squared_over_2)) * x_Bjorken * squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (5): Calculate the prefactor:
            prefactor = -tf.constant(8.0, dtype = tf.float32) * tf.sqrt(tf.constant(2.0, dtype = tf.float32) * y_quantity) * shorthand_k * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) / root_one_plus_epsilon_squared**5
            
            # (6): Calculate the coefficient:
            c_2_zero_plus_unp = prefactor * (tf.constant(1.0, dtype = tf.float32) + epsilon_squared_over_2) * bracket_term
            
            # (6.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_2_zero_plus_unp to be:\n{c_2_zero_plus_unp}")

            # (7): Return the coefficient:
            return c_2_zero_plus_unp

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_2_zero_plus_unp for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_2_zero_plus_unpolarized_V(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        shorthand_k: float,
        verbose: bool = False) -> float:
        try:

            # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
            root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

            # (2): Calculate the recurrent quantity t/Q^{2}:
            t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

            # (3): Calculate the annoying y quantity:
            y_quantity = tf.sqrt(tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32)))

            # (4): Calculate the prefactor:
            prefactor = tf.constant(8.0, dtype = tf.float32) * tf.sqrt(tf.constant(2.0, dtype = tf.float32)) * y_quantity * shorthand_k * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * x_Bjorken * t_over_Q_squared / root_one_plus_epsilon_squared**5
            
            # (5): Calculate the coefficient:
            c_2_zero_plus_unp_V = prefactor * (tf.constant(1.0, dtype = tf.float32) - (tf.constant(1.0, dtype = tf.float32) - tf.constant(2.0, dtype = tf.float32) * x_Bjorken) * t_over_Q_squared)
            
            # (5.1): If verbose, log the output:
            if verbose:
                tf.print(f"> Calculated c_2_zero_plus_unp_V to be:\n{c_2_zero_plus_unp_V}")

            # (6): Return the coefficient:
            return c_2_zero_plus_unp_V

        except Exception as ERROR:
            tf.print(f"> Error in calculating c_2_zero_plus_unp_V for Interference Term:\n> {ERROR}")
            return tf.constant(0.0, dtype = tf.float32)
        
    @tf.function
    def calculate_c_2_zero_plus_unpolarized_A(
        self,
        squared_Q_momentum_transfer: float, 
        x_Bjorken: float, 
        squared_hadronic_momentum_transfer_t: float,
        epsilon: float,
        lepton_energy_fraction_y: float, 
        t_prime: float,
        shorthand_k: float,
        verbose: bool = False) -> float:
        # (1): Calculate the recurrent quantity sqrt(1 + epsilon^2):
        root_one_plus_epsilon_squared = tf.sqrt(tf.constant(1.0, dtype = tf.float32) + epsilon**2)

        # (2): Calculate the recurrent quantity t/Q^{2}:
        t_over_Q_squared = squared_hadronic_momentum_transfer_t / squared_Q_momentum_transfer

        # (3): Calculate t'/Q^{2}
        t_prime_over_Q_squared = t_prime / squared_Q_momentum_transfer

        # (4): Calculate 1 - x_{B}:
        one_minus_xb = tf.constant(1.0, dtype = tf.float32) - x_Bjorken

        # (5): Calculate the annoying y quantity:
        y_quantity = tf.constant(1.0, dtype = tf.float32) - lepton_energy_fraction_y - (epsilon**2 * lepton_energy_fraction_y**2 / tf.constant(4.0, dtype = tf.float32))

        # (6): Calculate the bracket term:
        bracket_term = one_minus_xb + tf.constant(0.5, dtype = tf.float32) * t_prime_over_Q_squared * (tf.constant(4.0, dtype = tf.float32) * x_Bjorken * one_minus_xb + epsilon**2) / root_one_plus_epsilon_squared
        
        # (7): Calculate part of the prefactor:
        prefactor = tf.constant(8.0, dtype = tf.float32) * tf.sqrt(tf.constant(2.0, dtype = tf.float32) * y_quantity) * shorthand_k * (tf.constant(2.0, dtype = tf.float32) - lepton_energy_fraction_y) * t_over_Q_squared / root_one_plus_epsilon_squared**4
        
        # (8): Calculate the coefficient:
        c_2_zero_plus_unp_A = prefactor * bracket_term
        
        # (tf.constant(8.0, dtype = tf.float32)1): If verbose, log the output:
        if verbose:
            tf.print(f"> Calculated c_2_zero_plus_unp_A to be:\n{c_2_zero_plus_unp_A}")

        # (9): Return the coefficient:
        return c_2_zero_plus_unp_A

@register_keras_serializable()
class BSALayer(tf.keras.layers.Layer):

    def call(self, inputs):

        # (X): Unpack the inputs into the CFFs and the kinematics:
        kinematics, cffs = inputs

        # (X): Extract the eight CFFs from the DNN:
        real_H, imag_H, real_E, imag_E, real_Ht, imag_Ht, real_Et, imag_Et = tf.unstack(cffs, axis = -1)

        # (X): Extract the kinematics from the DNN:
        q_squared, x_bjorken, t, k, phi = tf.unstack(kinematics, axis = -1)

        # (X): DUMMY COMPUTATION FOR NOW:
        bsa = real_H**2 + imag_H**2 + tf.constant(0.5, dtype = tf.float32) * tf.cos(phi) * real_E + 0.1 * q_squared

        # (X): Re-cast the BSA into a single value (I think):
        return tf.expand_dims(bsa, axis = -1)

class SimultaneousFitModel(tf.keras.Model):

    def __init__(self, model):
        super(SimultaneousFitModel, self).__init__()

        self.model = model

    def train_step(self, data):
        """
        ## Description:
        This particular function is *required* if you are going to 
        inherit a tf Model class. 
        """

        # (X): Unpack the data:
        x_training_data, y_training_data = data

        if SETTING_DEBUG:
            print("> [DEBUG]: Unpacked training data.")

        # (X): Use TensorFlow's GradientTape to unfold each step of the training scheme:
        with tf.GradientTape() as gradient_tape:
            
            if SETTING_DEBUG:
                tf.print(f"> [DEBUG]: Now unraveling gradient tape...")

            # (X): Evaluate the model by passing in the input data:
            predicted_cff_values = self.model(x_training_data, training = True)

            if SETTING_DEBUG:
                tf.print(f"> [DEBUG]: Predicted CFF values: {predicted_cff_values}")

            # (X): Use the custom-defined loss function to compute a scalar loss:
            computed_loss = simultaneous_fit_loss(y_training_data, predicted_cff_values, x_training_data)

            if SETTING_DEBUG:
                tf.print(f"> [DEBUG]: Loss computed! {computed_loss}")

        # (X): Compute the gradients during backpropagation:
        computed_gradients = gradient_tape.gradient(computed_loss, self.trainable_variables)

        if SETTING_DEBUG:
            tf.print(f"> [DEBUG]: Computed batch gradients: {computed_gradients}")

        # (X): Call the TF model's optimizer:
        self.optimizer.apply_gradients(
            zip(
                computed_gradients,
                self.trainable_variables
            )
        )

        if SETTING_DEBUG:
            print("> [DEBUG]: Gradients applied with optimizer!")

def build_simultaneous_model():
    """
    ## Description:
    We initialize a DNN model used to predict the eight CFFs:
    """
    # (1): Initialize the Network with Uniform Random Sampling: [-0.1, -0.1]:
    initializer = tf.keras.initializers.RandomUniform(
        minval = -0.1,
        maxval = 0.1,
        seed = None)
    
    # (X): Define the input to the DNN:
    input_kinematics = Input(shape = (5, ), name = "input_layer")

    # (X): Pass the inputs through a densely-connected hidden layer:
    x = Dense(
        _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_1,
        activation = "relu",
        kernel_initializer = initializer)(input_kinematics)

    # (X): Pass the inputs through a densely-connected hidden layer:
    x = Dense(
        _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_2,
        activation = "relu",
        kernel_initializer = initializer)(x)

    # (X): Pass the inputs through a densely-connected hidden layer:
    x = Dense(
        _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_3,
        activation = "relu",
        kernel_initializer = initializer)(x)

    # (X): Pass the inputs through a densely-connected hidden layer:
    x = Dense(
        _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_4,
        activation = "relu",
        kernel_initializer = initializer)(x)

    # (X): Pass the inputs through a densely-connected hidden layer:
    output_cffs = tf.keras.layers.Dense(
        _HYPERPARAMETER_NUMBER_OF_NEURONS_LAYER_5,
        activation = "linear",
        kernel_initializer = initializer,
        name = "cff_output_layer")(x)
    
    # (4): Combine the kinematics as a single list:
    # kinematics_and_cffs = Concatenate(axis = 1)([input_kinematics, output_cffs])

    # (X): Concatenate the two:
    full_input = Concatenate(axis = -1)([input_kinematics, output_cffs])

    # (8): Compute, algorithmically, the cross section:
    cross_section_value = CrossSectionLayer()(full_input)

    # (8): Compute, algorithmically, the BSA:
    # | We are NOT READY FOR THIS YET:
    # bsa_value = BSALayer()([input_kinematics, output_cffs])

    # (9): Define the model as as Keras Model:
    simultaneous_fit_model = Model(
        inputs = input_kinematics,
        outputs = cross_section_value,
        name = "cross-section-model")

    if SETTING_DEBUG or SETTING_VERBOSE:
        print(simultaneous_fit_model.summary())

    # (X): Compile the model with a fixed learning rate using Adam and the custom loss:
    simultaneous_fit_model.compile(
        optimizer = tf.keras.optimizers.Adam(_HYPERPARAMETER_LEARNING_RATE),
        loss = tf.keras.losses.MeanSquaredError())

    # (X): Return the model:
    return simultaneous_fit_model