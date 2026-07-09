"""The single shared grocery-shopping rules block for product extraction.

Appendix A.4 fix: the legacy rich rules lived only in the per-item fallback
prompt while the batch prompt ran a thin summary, so the primary path used
weaker rules. Here there is ONE canonical block, imported by both the batch
prompt (P4) and the per-item fallback (P4-single) so they can never drift.
"""

PRODUCT_RULES = """\
GROCERY SHOPPING RULES

Goal: turn a parsed recipe ingredient into the grocery-store SEARCH TERM(s) and
the number of PACKAGES to buy (not the recipe amount).

1. American grocery-store naming. Translate UK/other terms to US supermarket terms:
   - courgette -> zucchini            - aubergine -> eggplant
   - rocket -> arugula                - coriander (leaves) -> cilantro
   - spring onions / scallions -> green onions
   - capsicum -> bell pepper          - mange tout -> snow peas
   - caster sugar -> granulated sugar - icing sugar -> powdered sugar
   - plain flour -> all-purpose flour - self-raising flour -> self-rising flour
   - bicarbonate of soda -> baking soda
   - double cream -> heavy cream      - single cream -> light cream
   - soured cream -> sour cream
   - prawns -> shrimp                 - mince / minced beef -> ground beef
   - minced pork -> ground pork       - gammon -> ham
   - passata -> tomato puree          - tinned -> canned
   - stock cube -> bouillon cube      - kitchen roll -> paper towels
   - chickpeas (dried) -> dried garbanzo beans

2. Fresh-prefix for PRODUCE and FRESH HERBS so results are raw produce, not a
   packaged/processed/seasoning product: "fresh cilantro", "fresh green onions",
   "fresh basil", "fresh ginger", "fresh mint", "fresh parsley". (Onions/garlic
   are produce too, but use plain "yellow onion"/"garlic" — those search cleanly.)

3. Beans/legumes default to CANNED unless the line says dry/dried/soaked:
   - "black beans" / "1 cup black beans" -> "canned black beans" (qty 1)
   - "kidney beans", "pinto beans", "cannellini beans", "chickpeas" -> canned
   - "dried black beans" / "dry chickpeas" -> "dried ..." (keep dried)

4. Package quantity = how the store sells it, reasoned from unit + food:
   - Produce sold individually: "2 limes" -> qty 2; "1 onion" -> qty 1.
   - Sold by bunch: "6 scallions"/"green onions" -> qty 1; "2 cups cilantro" -> qty 1.
   - Garlic by head: "3 cloves garlic" -> qty 1 (one head).
   - Eggs by carton: "2 eggs" -> qty 1.
   - Cans: "2 cans tomatoes" -> qty 2; "1 cup beans" -> qty 1 (one can).
   - Dairy by container: "0.5 cup heavy cream" -> qty 1.
   - Meat by package: "1 lb ground beef" -> qty 1; use target_size to hint size.

5. target_size (optional): when the parsed line implies a concrete purchase size
   (e.g. "2 lb chicken thighs", "14 oz can"), emit target_size (e.g. "2 lb",
   "14 oz") so ranking can prefer the right package. Omit when quantity is
   count-based (e.g. "2 limes") or unknowable.

6. Multiple options: decide ALTERNATIVES vs. ADDITIONS.
   - "or" (and parenthetical "(or X)") means ALTERNATIVES — the recipe accepts
     any one. Extract exactly ONE product: the FIRST-listed option. Do NOT buy
     every option.
       - "potatoes (russet or Yukon gold)" -> russet potatoes ONLY (one product).
       - "1 cup milk (or cream)" -> milk ONLY (one product).
       - "butter or margarine" -> butter ONLY.
   - "and" means ADDITIONS — the recipe needs both. Extract EACH as its own
     product.
       - "salt and pepper" -> two products (salt; black pepper).
   - EXCEPTION — the line explicitly asks for MULTIPLE at once
     ("preferably a mixture", "a mix of all", "any combination"): extract ALL
     the listed options even when joined by "or".
       - "cilantro, parsley, or mint, preferably a mixture" -> all three.
   - Commas that just list alternatives follow the "or" rule (one product);
     commas inside an explicit-mixture line follow the exception (all options).

7. "to taste" / garnish / unquantified -> qty 1 (one package).

8. confidence: 0.0-1.0 for how sure the search term is right; lower it for vague
   or ambiguous lines so the review UI can flag them.
"""
