package io.ppskit.questrunner

import java.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class BrspProofFixtureTest {
  @Test
  fun `JVM agrees with the shared BRSP role-bound proof fixture`() {
    val fixtureText =
        requireNotNull(javaClass.getResourceAsStream("/brsp1-proof.json")) {
              "Missing BRSP proof fixture."
            }
            .bufferedReader(Charsets.UTF_8)
            .use { it.readText() }
    val fixture = JSONObject(fixtureText)
    val secret = fixture.getString("secret")
    val transcript = fixture.getString("canonicalTranscript")

    assertEquals(
        fixture.getString("targetProof"),
        proof(secret, "target", transcript),
    )
    assertEquals(
        fixture.getString("controllerProof"),
        proof(secret, "controller", transcript),
    )
  }

  private fun proof(secret: String, role: String, transcript: String): String {
    val mac = Mac.getInstance("HmacSHA256")
    mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
    val value = mac.doFinal("BRSP/1 proof\n$role\n$transcript".toByteArray(Charsets.UTF_8))
    return Base64.getUrlEncoder().withoutPadding().encodeToString(value)
  }
}
