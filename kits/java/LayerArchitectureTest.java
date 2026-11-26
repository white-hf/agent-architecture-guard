package com.example.architecture;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

/**
 * Layer and domain rules (ArchUnit 1.3+, JUnit 5). Packages: com.example.<domain>.{web,application,domain,persistence}.
 * Replace com.example; keep the rules hard (no FreezingArchRule) once the code complies.
 */
class LayerArchitectureTest {
    private static final JavaClasses CLASSES = new ClassFileImporter()
            .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS).importPackages("com.example");

    @Test
    void domainLayerIsPlainJava() {
        noClasses().that().resideInAPackage("..domain..")
                .should().dependOnClassesThat().resideInAnyPackage("org.springframework..", "jakarta.persistence..",
                        "..application..", "..persistence..", "..web..")
                .check(CLASSES);
    }

    @Test
    void layersPointDownwards() {
        noClasses().that().resideInAPackage("..application..").should().dependOnClassesThat().resideInAPackage("..web..").check(CLASSES);
        noClasses().that().resideInAPackage("..persistence..").should().dependOnClassesThat().resideInAPackage("..web..").check(CLASSES);
        noClasses().that().resideInAPackage("..web..").should().dependOnClassesThat().resideInAPackage("..persistence..").check(CLASSES);
    }

    @Test
    void sqlOnlyInPersistence() {
        noClasses().that().resideOutsideOfPackage("..persistence..")
                .should().dependOnClassesThat().haveFullyQualifiedName("org.springframework.jdbc.core.JdbcTemplate")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate")
                .check(CLASSES);
    }

    @Test
    void domainsAreFreeOfCycles() {
        slices().matching("com.example.(*)..").should().beFreeOfCycles().check(CLASSES);
    }
}
