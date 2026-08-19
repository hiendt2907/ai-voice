import { MigrationInterface, QueryRunner } from "typeorm";

export class AddSttEngine1787115882216 implements MigrationInterface {
    name = 'AddSttEngine1787115882216'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "stt_settings" ADD "engine" character varying NOT NULL DEFAULT 'faster_whisper'`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "stt_settings" DROP COLUMN "engine"`);
    }

}
